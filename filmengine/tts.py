"""Turning lines of text into speech with Edge TTS, or with a Windows (SAPI)
voice such as Microsoft David, the voice many screen readers use.

Every spoken line is cached by its voice, words and settings, so making a
film again only fetches lines that changed.
"""

import asyncio
import hashlib
import json
import os
import subprocess

import edge_tts

from .errors import FilmError
from .paths import TTS_CACHE_DIR
from .voices import SAPI_PREFIX

MAX_AT_ONCE = 4
RETRIES = 3


def _clamp(value, low, high):
    return max(low, min(high, int(value)))


def speech_settings(rate, pitch):
    return f"{_clamp(rate, -90, 200):+d}%", f"{_clamp(pitch, -100, 100):+d}Hz"


def cache_path(voice, text, rate, pitch):
    rate_s, pitch_s = speech_settings(rate, pitch)
    key = hashlib.sha1(f"{voice}|{rate_s}|{pitch_s}|{text}".encode("utf-8")).hexdigest()[:20]
    return TTS_CACHE_DIR / (f"{key}.wav" if voice.startswith(SAPI_PREFIX) else f"{key}.mp3")


async def _speak(text, voice, rate, pitch, path, gate):
    rate_s, pitch_s = speech_settings(rate, pitch)
    async with gate:
        last_error = None
        for attempt in range(RETRIES):
            temp = path.with_suffix(".part")
            try:
                await edge_tts.Communicate(text, voice, rate=rate_s, pitch=pitch_s).save(str(temp))
                os.replace(temp, path)
                return None
            except edge_tts.exceptions.NoAudioReceived:
                return f'The voice made no sound for "{text}". Check the line has real words in it.'
            except Exception as e:  # network trouble: wait and try again
                last_error = e
                await asyncio.sleep(1.5 * (attempt + 1))
            finally:
                if temp.exists():
                    temp.unlink()
        return f"Couldn't reach the Microsoft voice service ({last_error}). Check the internet connection."


async def _speak_all(jobs, progress):
    gate = asyncio.Semaphore(MAX_AT_ONCE)

    async def one(job):
        error = await _speak(*job, gate)
        progress()
        return job, error

    return await asyncio.gather(*(one(j) for j in jobs))


SAPI_SCRIPT = r"""
Add-Type -AssemblyName System.Speech
$jobs = Get-Content -Raw -Encoding UTF8 $args[0] | ConvertFrom-Json
foreach ($job in $jobs) {
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $s.SelectVoice($job.voice)
    $s.Rate = $job.rate
    $s.SetOutputToWaveFile($job.path)
    $s.Speak($job.text)
    $s.Dispose()
}
"""


def _speak_sapi(jobs):
    """All Windows-voice lines in one PowerShell run. SAPI has no pitch setting."""
    job_file = TTS_CACHE_DIR / "sapi-jobs.json"
    script_file = TTS_CACHE_DIR / "sapi-speak.ps1"
    job_file.write_text(json.dumps([
        {"voice": voice[len(SAPI_PREFIX):], "rate": _clamp(round(rate / 10), -10, 10),
         "path": str(path), "text": text}
        for text, voice, rate, pitch, path in jobs]), encoding="utf-8")
    script_file.write_text(SAPI_SCRIPT, encoding="utf-8")
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-File", str(script_file), str(job_file)], capture_output=True, text=True)
    missing = [job for job in jobs if not job[4].exists()]
    if missing:
        raise FilmError(f'The Windows voice could not say "{missing[0][0]}".\n{result.stderr.strip()[:500]}')


def synthesize(requests, progress=lambda done, total: None):
    """requests: list of (text, voice, rate, pitch). Returns {request: audio file path}."""
    TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    paths = {r: cache_path(r[1], r[0], r[2], r[3]) for r in requests}
    todo = [(r[0], r[1], r[2], r[3], paths[r]) for r in dict.fromkeys(requests) if not paths[r].exists()]
    windows = [job for job in todo if job[1].startswith(SAPI_PREFIX)]
    online = [job for job in todo if not job[1].startswith(SAPI_PREFIX)]
    if windows:
        _speak_sapi(windows)
    if online:
        done = [0]

        def tick():
            done[0] += 1
            progress(done[0], len(online))

        results = asyncio.run(_speak_all(online, tick))
        errors = [error for _, error in results if error]
        if errors:
            raise FilmError(errors[0] if len(errors) == 1 else
                            f"{len(errors)} lines could not be spoken. The first problem was:\n{errors[0]}")
    return paths
