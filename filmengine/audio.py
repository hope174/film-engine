"""Loading, saving and basic shaping of audio.

All audio inside the engine is a float32 numpy array of shape (samples, 2)
at SAMPLE_RATE, with values roughly between -1 and 1.
"""

import os
import shutil
import subprocess
from pathlib import Path

import miniaudio
import numpy as np
import soundfile

from .errors import FilmError

SAMPLE_RATE = 44100
AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".opus", ".wma", ".aif", ".aiff"}


def find_ffmpeg():
    found = shutil.which("ffmpeg")
    if found:
        return found
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    links = local / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
    if links.exists():
        return str(links)
    packages = local / "Microsoft" / "WinGet" / "Packages"
    if packages.exists():
        for candidate in packages.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe"):
            return str(candidate)
    return None


def silence(seconds):
    return np.zeros((max(0, int(round(seconds * SAMPLE_RATE))), 2), dtype=np.float32)


def seconds(audio):
    return len(audio) / SAMPLE_RATE


def load(path):
    """Read any common audio file as stereo float32 at SAMPLE_RATE."""
    path = Path(path)
    try:
        decoded = miniaudio.decode_file(
            str(path), output_format=miniaudio.SampleFormat.FLOAT32,
            nchannels=2, sample_rate=SAMPLE_RATE,
        )
        return np.asarray(decoded.samples, dtype=np.float32).reshape(-1, 2)
    except Exception:
        pass
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise FilmError(
            f"I can't read the sound file {path.name}. Try saving it as a WAV or MP3 file, "
            "or install ffmpeg so more file types work."
        )
    result = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(SAMPLE_RATE), "-"],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise FilmError(f"I can't read the sound file {path.name}. It may be damaged or not a sound file.")
    return np.frombuffer(result.stdout, dtype=np.float32).reshape(-1, 2).copy()


def save(audio, path, title=None):
    """Save as .wav, .ogg or .mp3 (mp3 needs ffmpeg). Returns the path actually written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    audio = np.clip(audio, -1.0, 1.0).astype(np.float32)
    suffix = path.suffix.lower()
    if suffix in (".mp3", ".ogg"):
        ffmpeg = find_ffmpeg()
        if ffmpeg:
            command = [ffmpeg, "-y", "-v", "error", "-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", "2", "-i", "-"]
            if title:
                command += ["-metadata", f"title={title}"]
            command += (["-b:a", "192k"] if suffix == ".mp3" else ["-c:a", "libvorbis", "-q:a", "6"]) + [str(path)]
            result = subprocess.run(command, input=audio.tobytes(), capture_output=True)
            if result.returncode == 0:
                return path
        if suffix == ".ogg":
            # libsndfile's Vorbis encoder crashes on big writes, so feed it small pieces.
            with soundfile.SoundFile(str(path), "w", SAMPLE_RATE, 2, format="OGG", subtype="VORBIS") as f:
                for i in range(0, len(audio), 4096):
                    f.write(audio[i:i + 4096])
            return path
        path = path.with_suffix(".wav")  # no ffmpeg: fall back to WAV
    soundfile.write(str(path), audio, SAMPLE_RATE, subtype="PCM_16")
    return path


def fade(audio, fade_in=0.0, fade_out=0.0):
    audio = audio.copy()
    n = len(audio)
    fi = min(n, int(fade_in * SAMPLE_RATE))
    fo = min(n, int(fade_out * SAMPLE_RATE))
    if fi > 0:
        audio[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)[:, None]
    if fo > 0:
        audio[n - fo:] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)[:, None]
    return audio


def trim(audio, skip=0.0, length=None):
    start = int(skip * SAMPLE_RATE)
    audio = audio[start:]
    if length is not None:
        audio = audio[: int(length * SAMPLE_RATE)]
    return audio


def loop_to(audio, total_samples):
    if len(audio) == 0 or total_samples <= 0:
        return np.zeros((max(total_samples, 0), 2), dtype=np.float32)
    repeats = int(np.ceil(total_samples / len(audio)))
    return np.tile(audio, (repeats, 1))[:total_samples]
