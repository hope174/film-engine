"""Turns a parsed Script into finished audio files."""

import difflib
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import audio, builtin_sounds, effects, tts, voices
from .audio import SAMPLE_RATE
from .errors import FilmError, ScriptErrors, ScriptProblem
from .paths import SHARED_SOUNDS_DIR, SOUND_FOLDERS_FILE
from .script import Line, Pause, Scene, Sound, StartChannel, Stop

DEFAULT_STOP_FADE = 1.0
DUCK_LEVEL = 0.35  # music under speech drops to this share of its volume
RECORDING_FOLDERS = ("voice", "recordings")


@dataclass
class Placed:
    start: float
    audio: np.ndarray


@dataclass
class Running:
    channel: str
    name: str
    start: float
    audio: np.ndarray
    options: object
    end: float | None = None
    fade_out: float = DEFAULT_STOP_FADE


def _fmt_time(seconds):
    minutes, secs = divmod(max(0.0, seconds), 60)
    return f"{int(minutes)}:{secs:04.1f}"


def extra_sound_folders():
    """Folders listed in sound-folders.txt, one per line, such as a music library."""
    if not SOUND_FOLDERS_FILE.exists():
        return []
    folders = []
    for line in SOUND_FOLDERS_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip().strip('"')
        if line and not line.startswith("#"):
            folders.append(Path(line).expanduser())
    return folders


class SoundFinder:
    """Finds sound files by name: first in the film's own folder, then the shared
    sounds folder, then any folders listed in sound-folders.txt."""

    def __init__(self, film_dir):
        self.folders = [film_dir / "sounds", film_dir, SHARED_SOUNDS_DIR] + extra_sound_folders()
        self.loaded = {}
        self._index = None

    def index(self):
        if self._index is None:
            self._index = {}
            for folder in self.folders:
                if not folder.is_dir():
                    continue
                for f in sorted(folder.rglob("*")):
                    if (f.suffix.lower() in audio.AUDIO_EXTENSIONS and "output" not in f.parts
                            and not any(r in f.parts for r in RECORDING_FOLDERS)):
                        self._index.setdefault(f.stem.lower(), f)
        return self._index

    def path_for(self, name):
        wanted = Path(name)
        has_ext = wanted.suffix.lower() in audio.AUDIO_EXTENSIONS
        for folder in self.folders:
            if has_ext and (folder / wanted).is_file():
                return folder / wanted
            if not has_ext and len(wanted.parts) > 1:  # "ondrosik/Whispered"
                for ext in audio.AUDIO_EXTENSIONS:
                    if (folder / f"{name}{ext}").is_file():
                        return folder / f"{name}{ext}"
        return self.index().get((wanted.stem if has_ext else wanted.name).lower())

    def find(self, name):
        """Returns audio, or raises FilmError with suggestions."""
        key = name.lower()
        if key not in self.loaded:
            found = self.path_for(name)
            if found is not None:
                clip = audio.load(found)
            else:
                clip = builtin_sounds.get(Path(name).stem)
                if clip is None:
                    raise FilmError(self._missing_message(name))
            self.loaded[key] = clip
        return self.loaded[key]

    def _missing_message(self, name):
        known = sorted(set(self.index()) | set(builtin_sounds.BUILTIN))
        close = difflib.get_close_matches(Path(name).stem.lower(), known, n=3, cutoff=0.5)
        message = (f'I can\'t find a sound called "{name}". Put the sound file in the film\'s sounds folder '
                   f"or in the shared sounds folder.")
        if close:
            message += " Did you mean " + " or ".join(close) + "?"
        return message


def line_ids(script):
    """Every spoken line gets an id: L001, L002... in the order they appear."""
    ids = {}
    for event in script.events:
        if isinstance(event, Line):
            ids[id(event)] = f"L{len(ids) + 1:03d}"
    return ids


def recording_for(film_dir, line_id):
    """A recorded take that replaces a generated line, such as voice/L012.wav."""
    for folder in RECORDING_FOLDERS:
        for ext in audio.AUDIO_EXTENSIONS:
            path = film_dir / folder / f"{line_id}{ext}"
            if path.is_file():
                return path
    return None


def write_lines_file(script, ids):
    rows = [f"{ids[id(e)]}  {script.cast[e.speaker].name}: {e.text}" for e in script.events if isinstance(e, Line)]
    (script.path.parent / "lines.txt").write_text(
        "Every line in the film. To replace one with a recording, save it in the voice folder named by its id, "
        "for example voice/L012.wav, then make the film again.\n"
        "The ids follow the order of the lines, so adding a line earlier in the script changes the ids after it.\n\n"
        + "\n".join(rows) + "\n", encoding="utf-8")


def _check(script, finder):
    problems = []
    resolved = {}
    for key, member in script.cast.items():
        try:
            resolved[key] = voices.resolve(member.voice)
        except FilmError as e:
            problems.append(ScriptProblem(member.line_number, "", f"The voice for {member.name}: {e}"))
    for event in script.events:
        if isinstance(event, (Sound, StartChannel)):
            try:
                finder.find(event.name)
            except FilmError as e:
                problems.append(ScriptProblem(event.line_number, "", str(e)))
    if problems:
        raise ScriptErrors(sorted(problems, key=lambda p: p.line_number))
    return resolved


def check(script):
    """Look for problems that need the voice list and sound files. Raises ScriptErrors."""
    _check(script, SoundFinder(script.path.parent))


def render(script, output_base, formats, say=print):
    """Make the film. output_base is the file path without an ending. Returns (paths, seconds)."""
    film_dir = script.path.parent
    finder = SoundFinder(film_dir)
    cast_voices = _check(script, finder)
    ids = line_ids(script)
    write_lines_file(script, ids)

    # 1. Speak every line (cached lines are reused, recorded takes replace generated ones).
    requests = {}
    recorded = {}
    for event in script.events:
        if isinstance(event, Line):
            take = recording_for(film_dir, ids[id(event)])
            if take:
                recorded[id(event)] = take
                continue
            opts = script.cast[event.speaker].options.combined_with(event.options)
            requests[id(event)] = (event.text, cast_voices[event.speaker], opts.rate, opts.pitch)
    if recorded:
        say(f"Using {len(recorded)} recorded lines from the voice folder.")
    unique = set(requests.values())
    new = sum(not tts.cache_path(r[1], r[0], r[2], r[3]).exists() for r in unique)
    say(f"Getting voices for {new} new lines. {len(unique) - new} lines are saved from last time.")
    speech = tts.synthesize(list(requests.values()), progress=lambda done, total: say(
        f"  spoken {done} of {total}") if done % 5 == 0 or done == total else None)

    # 2. Lay everything out on a timeline.
    placed = []
    running = {}
    finished = []
    speech_spans = []
    log = []
    t = 0.0
    last_line_start = 0.0
    last_was_line = False

    def stop_channel(key, at, fade):
        item = running.pop(key)
        item.end = at
        if fade is not None:
            item.fade_out = fade
        finished.append(item)

    for event in script.events:
        if isinstance(event, Line):
            member = script.cast[event.speaker]
            opts = member.options.combined_with(event.options)
            if id(event) in recorded:
                clip = audio.load(recorded[id(event)])
            else:
                clip = audio.load(speech[requests[id(event)]])
            spoken_length = audio.seconds(clip)
            clip = _shape(clip, opts)
            start = (last_line_start if opts.overlap else t) + opts.delay
            placed.append(Placed(start, clip))
            speech_spans.append((start, start + spoken_length))
            log.append(f"{_fmt_time(start)}  {ids[id(event)]}  {member.name}: {event.text}")
            last_line_start = start
            end = start + spoken_length + script.gap
            t = max(t, end) if opts.overlap or opts.nowait else end
            last_was_line = True
        elif isinstance(event, Sound):
            opts = event.options
            clip = _shape(audio.trim(finder.find(event.name), opts.skip, opts.length), opts)
            start = t + opts.delay
            if last_was_line and not opts.nowait:
                start = max(0.0, start - script.gap / 2)  # a sound needs less gap than speech
            placed.append(Placed(start, clip))
            log.append(f"{_fmt_time(start)}  [sound: {event.name}]")
            if not opts.nowait:
                t = start + audio.seconds(clip)
            last_was_line = False
        elif isinstance(event, StartChannel):
            opts = event.options
            if event.channel in running:
                stop_channel(event.channel, t, max(opts.fade_in, 0.5))
            clip = audio.trim(finder.find(event.name), opts.skip, opts.length)
            if opts.reverse:
                clip = clip[::-1]
            clip = effects.apply(clip, opts.effects)
            if opts.movement is None:
                clip = effects.position(clip, opts.angle, opts.distance)
            running[event.channel] = Running(event.channel, event.name, t + opts.delay, clip, opts,
                                             fade_out=opts.fade_out if opts.fade_out is not None else DEFAULT_STOP_FADE)
            log.append(f"{_fmt_time(t)}  [{event.channel} starts: {event.name}]")
            last_was_line = False
        elif isinstance(event, Stop):
            targets = list(running) if event.target == "all" else [
                key for key, item in running.items()
                if event.target in (key, Path(item.name).stem.lower(), item.name.lower())]
            if not targets:
                log.append(f"{_fmt_time(t)}  [stop {event.target}: nothing was playing]")
            for key in targets:
                stop_channel(key, t, event.fade_out)
                log.append(f"{_fmt_time(t)}  [{key} stops]")
            last_was_line = False
        elif isinstance(event, Pause):
            t += event.seconds
            last_was_line = False
        elif isinstance(event, Scene):
            log.append(f"{_fmt_time(t)}  Scene: {event.name}")

    if last_was_line:
        t -= script.gap
    total = t + script.ending
    for key in list(running):
        stop_channel(key, total, max(DEFAULT_STOP_FADE, min(script.ending, 3.0)))
    total = max([total] + [p.start + audio.seconds(p.audio) for p in placed])

    # 3. Mix.
    say("Mixing...")
    n = int(np.ceil(total * SAMPLE_RATE)) + 1
    mix = np.zeros((n, 2), dtype=np.float32)
    for p in placed:
        _add(mix, p.audio, p.start)
    duck = _duck_envelope(speech_spans, n)
    for item in finished:
        start = max(item.start, 0.0)
        length = int((item.end - start) * SAMPLE_RATE)
        if length <= 0:
            continue
        opts = item.options
        clip = audio.loop_to(item.audio, length) if opts.loop else item.audio[:length]
        if opts.movement is not None:  # moves across the whole time it plays
            clip = effects.position(clip, opts.angle, opts.distance, opts.movement)
        fade_out = min(item.fade_out, audio.seconds(clip))
        clip = audio.fade(clip, opts.fade_in, fade_out) * opts.gain * _default_level(item.channel)
        # Music dips under speech unless told "no duck"; other sounds only if told "duck".
        if opts.duck if opts.duck is not None else item.channel == "music":
            i = int(start * SAMPLE_RATE)
            clip = clip * duck[i:i + len(clip)][:, None]
        _add(mix, clip, start)

    peak = float(np.abs(mix).max())
    if peak > 0:
        mix *= 0.89 / peak  # about -1 dB: as loud as possible without clipping

    written = [audio.save(mix, Path(f"{output_base}.{fmt}"), title=script.title) for fmt in formats]
    timeline_path = Path(f"{output_base} - timeline.txt")
    timeline_path.write_text(
        f"{script.title}\nLength {_fmt_time(total)}\n\n" + "\n".join(log) + "\n", encoding="utf-8")
    return list(dict.fromkeys(written)), total


def _shape(clip, opts):
    if opts.reverse:
        clip = clip[::-1]
    clip = effects.apply(clip, opts.effects)
    clip = effects.position(clip, opts.angle, opts.distance, opts.movement)
    clip = audio.fade(clip, opts.fade_in, opts.fade_out or 0.0)
    return (clip * opts.gain).astype(np.float32)


def _default_level(channel):
    # Background sounds sit under the voices unless the script sets a volume.
    return {"music": 0.5, "ambience": 0.45, "background": 0.45}.get(channel, 1.0)


def _add(mix, clip, start):
    i = int(round(max(start, 0) * SAMPLE_RATE))
    piece = clip[: max(0, len(mix) - i)]
    mix[i:i + len(piece)] += piece


def _duck_envelope(spans, n):
    """1.0 when nobody speaks, DUCK_LEVEL while someone speaks, with smooth changes."""
    block = SAMPLE_RATE // 100  # 10 ms steps
    blocks = n // block + 2
    speaking = np.zeros(blocks)
    for start, end in spans:
        speaking[int(start * 100):int(end * 100) + 1] = 1.0
    kernel = np.ones(30) / 30  # changes take about 0.3 seconds
    smooth = np.clip(np.convolve(speaking, kernel, mode="same") * 2, 0, 1)
    levels = 1.0 - (1.0 - DUCK_LEVEL) * smooth
    return np.repeat(levels, block)[:n].astype(np.float32)


def safe_filename(title):
    cleaned = re.sub(r'[<>:"/\\|?*]', "", title).strip(" .")
    return cleaned or "film"
