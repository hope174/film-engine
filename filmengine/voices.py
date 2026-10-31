"""Finding Edge voices by full name (en-GB-RyanNeural) or short name (Ryan)."""

import asyncio
import json
import re
import subprocess

import edge_tts

from .errors import FilmError
from .paths import CACHE_DIR

VOICE_CACHE = CACHE_DIR / "voices.json"
FULL_NAME = re.compile(r"^[a-z]{2,3}-[A-Za-z0-9]+(-[A-Za-z0-9]+)*Neural$", re.IGNORECASE)
PREFERRED_LOCALES = ["en-US", "en-GB", "en-AU", "en-CA", "en-IE", "en-NZ", "en-IN", "en-ZA"]


def all_voices(refresh=False):
    if VOICE_CACHE.exists() and not refresh:
        try:
            return json.loads(VOICE_CACHE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    try:
        voices = asyncio.run(edge_tts.list_voices())
    except Exception as e:
        raise FilmError(
            "I couldn't get the list of voices from Microsoft. Check the internet connection and try again."
            f"\n(Details: {e})"
        )
    keep = [{"name": v["ShortName"], "gender": v.get("Gender", ""), "locale": v.get("Locale", ""),
             "language": v.get("FriendlyName", "")} for v in voices]
    VOICE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    VOICE_CACHE.write_text(json.dumps(keep, indent=1), encoding="utf-8")
    return keep


def short_name(full):
    """en-GB-RyanNeural -> Ryan ; en-US-AndrewMultilingualNeural -> AndrewMultilingual"""
    if full.startswith(SAPI_PREFIX):
        return full[len(SAPI_PREFIX):]
    return full.split("-")[-1].removesuffix("Neural")


SAPI_PREFIX = "sapi:"
_sapi_cache = None


def sapi_voices():
    """The Windows voices a screen reader uses, such as Microsoft David Desktop."""
    global _sapi_cache
    if _sapi_cache is None:
        command = ("Add-Type -AssemblyName System.Speech; "
                   "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | "
                   "Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo.Name }")
        try:
            result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                                    capture_output=True, text=True, timeout=60)
            _sapi_cache = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except (OSError, subprocess.SubprocessError):
            _sapi_cache = []
    return _sapi_cache


def _find_sapi(wanted):
    words = wanted.lower().replace(SAPI_PREFIX, "").replace("sapi", "").split()
    for name in sapi_voices():
        if words and all(w in name.lower() for w in words):
            return SAPI_PREFIX + name
    return None


def resolve(voice):
    """Turn what the script wrote into a real voice name. Raises FilmError with suggestions."""
    wanted = voice.strip()
    if wanted.lower().startswith(("sapi", "microsoft ", "windows ")):
        found = _find_sapi(wanted.lower().removeprefix("windows "))
        if found:
            return found
        installed = ", ".join(sapi_voices()) or "none"
        raise FilmError(f'There is no Windows voice called "{wanted}". The Windows voices on this computer are: {installed}.')
    voices = all_voices()
    names = {v["name"].lower(): v["name"] for v in voices}

    if wanted.lower() in names:
        return names[wanted.lower()]
    if FULL_NAME.match(wanted):
        raise FilmError(f'There is no voice called "{wanted}". ' + _suggest(wanted, voices))

    matches = [v for v in voices if short_name(v["name"]).lower() == wanted.lower().replace(" ", "")]
    if not matches:
        found = _find_sapi(wanted)  # "David" or "Zira" can mean the Windows voice
        if found:
            return found
        raise FilmError(f'I can\'t find a voice called "{wanted}". ' + _suggest(wanted, voices))

    def rank(v):
        locale = v["locale"]
        return PREFERRED_LOCALES.index(locale) if locale in PREFERRED_LOCALES else len(PREFERRED_LOCALES)

    return sorted(matches, key=rank)[0]["name"]


def _suggest(wanted, voices):
    import difflib
    shorts = sorted({short_name(v["name"]) for v in voices if v["locale"].startswith("en-")})
    close = difflib.get_close_matches(short_name(wanted) if "-" in wanted else wanted, shorts, n=3, cutoff=0.5)
    if close:
        return "Did you mean " + " or ".join(close) + "? Run List voices to see them all."
    return "Run List voices to see every voice you can use."


def describe(v):
    return f'{v["name"]}, {v["gender"].lower()}, {v["locale"]}. Short name: {short_name(v["name"])}'
