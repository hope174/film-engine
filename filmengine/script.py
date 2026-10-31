"""Reads a film script (plain text) into a list of events.

The script format is described for writers in "Script guide.txt". In short:

    Title: The Lighthouse
    Narrator = Ryan
    Mara = en-US-AriaNeural, rate -10%

    [ambience: rain, loop, volume 30]
    Narrator: It was a dark night.
    Mara (whisper, echo): Is anyone there?
    [sound: knock]
    [pause 2]
    [stop ambience, fade out 3]
"""

import difflib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from .effects import EFFECTS
from .errors import ScriptErrors, ScriptProblem

# Words that change how a voice speaks. Each maps to adjustments that are
# added together: rate (percent), pitch (Hz), gain (multiplier), effects.
SPEECH_STYLES = {
    "slow": {"rate": -20},
    "very slow": {"rate": -40},
    "fast": {"rate": 20},
    "very fast": {"rate": 40},
    "high": {"pitch": 20},
    "very high": {"pitch": 40},
    "low": {"pitch": -20},
    "deep": {"pitch": -20},
    "very low": {"pitch": -35},
    "very deep": {"pitch": -35},
    "quiet": {"gain": 0.5},
    "very quiet": {"gain": 0.25},
    "soft": {"gain": 0.6},
    "loud": {"gain": 1.5},
    "very loud": {"gain": 2.0},
    "whisper": {"rate": -10, "gain": 0.6, "effects": ["whisper"]},
    "shout": {"rate": 5, "pitch": 5, "gain": 1.4, "effects": ["drive"]},
    "monster": {"rate": -15, "pitch": -45, "effects": ["monster"]},
    "child": {"pitch": 35, "rate": 5},
    "old": {"pitch": -10, "rate": -15},
    "thinking": {"gain": 0.8, "effects": ["thought"]},
    "sad": {"rate": -15, "pitch": -8, "gain": 0.8},
    "excited": {"rate": 15, "pitch": 10, "gain": 1.2},
    "nervous": {"rate": 10, "pitch": 6},
}

SYNONYMS = {
    "whispering": "whisper", "whispers": "whisper", "whispered": "whisper",
    "shouting": "shout", "shouts": "shout", "yell": "shout", "yelling": "shout",
    "scream": "shout", "screaming": "shout",
    "echoing": "echo", "echoes": "echo",
    "slowly": "slow", "quickly": "fast", "quick": "fast",
    "quietly": "quiet", "loudly": "loud", "softly": "soft",
    "thought": "thinking", "thinks": "thinking", "inner voice": "thinking",
    "on the phone": "telephone", "phone": "telephone",
    "on the radio": "radio",
    "distant": "far", "far away": "far", "in the distance": "far",
    "muffled": "muffled", "through a wall": "muffled", "behind door": "muffled",
    "flashback": "dream", "memory": "dream", "dreaming": "dream",
    "robotic": "robot", "ghostly": "ghost", "cavern": "cave",
    "middle": "center", "centre": "center",
    "don't wait": "nowait", "dont wait": "nowait", "no wait": "nowait",
    "with next": "nowait", "keep going": "nowait",
    "at the same time": "overlap", "together": "overlap", "same time": "overlap",
    "looping": "loop", "repeat": "loop", "loops": "loop", "play once": "once", "no loop": "once",
    "backwards": "reverse", "reversed": "reverse",
    "ducking": "duck",
    "discord": "voice chat", "on discord": "voice chat", "on teamtalk": "voice chat", "voicechat": "voice chat",
    "pa": "announcer", "stadium": "announcer", "loudspeaker": "announcer", "tannoy": "announcer",
    "behind the door": "muffled", "behind a door": "muffled", "door": "muffled",
}

FLAGS = {"loop", "once", "nowait", "overlap", "duck", "reverse"}

# Where a sound is heard from, as an angle around the listener:
# 0 is straight ahead, 90 is the right ear, -90 the left ear, 180 behind.
POSITION_WORDS = {
    "center": 0, "ahead": 0, "front": 0, "in front": 0,
    "left": -60, "far left": -90, "right": 60, "far right": 90,
    "front left": -35, "front right": 35, "ahead left": -35, "ahead right": 35,
    "behind": 180, "behind left": -135, "behind right": 135,
    "back left": -135, "back right": 135,
}
DISTANCE_WORDS = {"close": 0.6, "near": 0.6, "very close": 0.35, "nearby": 0.8}
MOVEMENTS = {
    "move left to right": "left to right", "left to right": "left to right",
    "move right to left": "right to left", "right to left": "right to left",
    "coming closer": "closer", "approaching": "closer", "getting closer": "closer",
    "going away": "away", "moving away": "away", "leaving": "away", "getting further": "away",
}

# "fade in 2", "delay 1.5 seconds", "volume 40%", "volume -6 db", "gain -6",
# "rate -10%", "pitch +5hz", "pan -50", "angle 120", "distance 2"
NUMBER_SETTINGS = re.compile(
    r"^(fade in|fade out|delay|skip|length|volume|gain|rate|speed|pitch|pan|angle|distance)\s*:?\s*"
    r"([+-]?\d+(?:\.\d+)?)\s*(%|hz|db|s|sec|secs|second|seconds)?$"
)

AUDIO_CHANNELS = {"music": "music", "ambience": "ambience", "ambient": "ambience",
                  "background": "background", "atmosphere": "ambience"}
SOUND_WORDS = {"sound", "sfx", "effect sound", "sound effect", "play"}
SETTINGS = {"title", "gap", "ending", "format", "cast", "scene", "note", "notes", "author", "by"}


def all_option_words():
    return sorted(set(SPEECH_STYLES) | set(SYNONYMS) | FLAGS | set(POSITION_WORDS) | set(DISTANCE_WORDS)
                  | set(MOVEMENTS) | set(EFFECTS) | {"no duck"})


@dataclass
class Options:
    effects: list = field(default_factory=list)
    gain: float = 1.0
    rate: int = 0
    pitch: int = 0
    angle: float | None = None
    distance: float | None = None
    movement: str | None = None
    loop: bool = False
    once: bool = False
    nowait: bool = False
    overlap: bool = False
    duck: bool | None = None
    reverse: bool = False
    fade_in: float = 0.0
    fade_out: float | None = None
    delay: float = 0.0
    skip: float = 0.0
    length: float | None = None

    def combined_with(self, other):
        """Cast options plus line options: numbers add up, effects stack."""
        merged = Options(**{k: getattr(other, k) for k in self.__dataclass_fields__})
        merged.effects = self.effects + other.effects
        merged.gain = self.gain * other.gain
        merged.rate = self.rate + other.rate
        merged.pitch = self.pitch + other.pitch
        for name in ("angle", "distance", "movement"):
            if getattr(other, name) is None:
                setattr(merged, name, getattr(self, name))
        return merged


class OptionError(Exception):
    pass


def _apply_word(opts, word):
    word = SYNONYMS.get(word, word)
    if word in SPEECH_STYLES:
        style = SPEECH_STYLES[word]
        opts.rate += style.get("rate", 0)
        opts.pitch += style.get("pitch", 0)
        opts.gain *= style.get("gain", 1.0)
        opts.effects += style.get("effects", [])
    elif word in EFFECTS:
        opts.effects.append(word)
    elif word in POSITION_WORDS:
        opts.angle = POSITION_WORDS[word]
    elif word in DISTANCE_WORDS:
        opts.distance = DISTANCE_WORDS[word]
    elif word in MOVEMENTS:
        opts.movement = MOVEMENTS[word]
    elif word in FLAGS:
        setattr(opts, word, True)
    elif word in ("no duck", "don't duck", "dont duck"):
        opts.duck = False
    elif word in ("normal", "none", ""):
        pass
    else:
        return False
    return True


def _apply_number(opts, match):
    name, value, unit = match.group(1), float(match.group(2)), match.group(3)
    if name == "gain" or unit == "db":
        opts.gain *= 10 ** (value / 20.0)  # decibels: -6 is about half as loud
    elif name == "volume":
        opts.gain *= max(value, 0) / 100.0
    elif name in ("rate", "speed"):
        opts.rate += int(value)
    elif name == "pitch":
        opts.pitch += int(value)
    elif name == "pan":
        opts.angle = math.degrees(math.asin(max(-1.0, min(1.0, value / 100.0))))
    elif name == "angle":
        opts.angle = value
    elif name == "distance":
        opts.distance = max(0.1, value)
    elif name == "fade in":
        opts.fade_in = value
    elif name == "fade out":
        opts.fade_out = value
    elif name == "delay":
        opts.delay = value
    elif name == "skip":
        opts.skip = value
    elif name == "length":
        opts.length = value


def parse_options(text):
    """Parse 'whisper, echo, volume 50' into Options. Raises OptionError."""
    opts = Options()
    pieces = re.split(r",|;|\band\b", text.lower())
    for piece in pieces:
        piece = " ".join(piece.replace("â€™", "'").split())
        if not piece:
            continue
        match = NUMBER_SETTINGS.match(piece)
        if match:
            _apply_number(opts, match)
            continue
        if _apply_word(opts, piece):
            continue
        # Allow several plain words in one piece, such as "slow whisper".
        words = piece.split()
        trial = Options()
        if len(words) > 1 and all(_apply_word(trial, w) for w in words):
            for w in words:
                _apply_word(opts, w)
            continue
        raise OptionError(_unknown_word_message(piece))
    return opts


def _unknown_word_message(piece):
    setting = re.match(r"^(fade in|fade out|delay|skip|length|volume|gain|rate|speed|pitch|pan|angle|distance)\b", piece)
    if setting:
        return f'"{piece}" needs a number written in digits, like  {setting.group(1)} 2'
    words = difflib.get_close_matches(piece, all_option_words(), n=6, cutoff=0.6)
    close = list(dict.fromkeys(SYNONYMS.get(w, w) for w in words))[:3]
    message = f'I don\'t understand "{piece}".'
    if close:
        message += " Did you mean " + " or ".join(f'"{c}"' for c in close) + "?"
    else:
        message += " Script guide.txt lists all the words you can use."
    return message


# ---------------------------------------------------------------- events

@dataclass
class CastMember:
    name: str
    voice: str
    options: Options
    line_number: int


@dataclass
class Line:
    speaker: str        # the cast key (lower case)
    text: str
    options: Options
    line_number: int


@dataclass
class Sound:
    name: str
    options: Options
    line_number: int


@dataclass
class StartChannel:
    channel: str
    name: str
    options: Options
    line_number: int


@dataclass
class Stop:
    target: str          # channel name, sound name or "all"
    fade_out: float | None
    line_number: int


@dataclass
class Pause:
    seconds: float
    line_number: int


@dataclass
class Scene:
    name: str
    line_number: int


@dataclass
class Script:
    path: Path
    title: str
    cast: dict
    events: list
    gap: float = 0.5
    ending: float = 3.0
    formats: list = field(default_factory=lambda: ["mp3"])


CAST_LINE = re.compile(r"^([^:=\[\]()]{1,40}?)\s*=\s*(.+)$")
DIALOGUE_LINE = re.compile(r"^([^:=\[\]()]{1,40}?)\s*(?:\(([^)]*)\))?\s*:\s*(.*)$")
SECONDS = re.compile(r"^:?\s*(\d+(?:\.\d+)?)\s*(s|sec|secs|second|seconds)?$")


def read_text(path):
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_script(path):
    path = Path(path)
    lines = read_text(path).splitlines()
    problems = []
    cast = {}

    def problem(number, message):
        problems.append(ScriptProblem(number, lines[number - 1], message))

    # First pass: the cast, so we know which names are characters.
    for number, raw in enumerate(lines, 1):
        text = _strip_note(raw)
        match = CAST_LINE.match(text)
        if not match or text.startswith("["):
            continue
        name = match.group(1).strip()
        parts = match.group(2).split(",", 1)
        voice = parts[0].strip()
        try:
            options = parse_options(parts[1]) if len(parts) > 1 else Options()
        except OptionError as e:
            problem(number, f"In the voice for {name}: {e}")
            options = Options()
        if name.lower() in cast:
            problem(number, f"{name} is in the cast twice. Keep only one line for them.")
        cast[name.lower()] = CastMember(name, voice, options, number)

    script = Script(path=path, title=path.parent.name, cast=cast, events=[])

    # Second pass: everything else.
    last_line = None
    for number, raw in enumerate(lines, 1):
        text = _strip_note(raw)
        if not text:
            last_line = None
            continue
        if CAST_LINE.match(text) and not text.startswith("["):
            last_line = None
            continue
        try:
            if text.startswith("["):
                if not text.endswith("]"):
                    raise OptionError("This line starts with [ but does not end with ]. Add a ] at the end.")
                script.events.append(_parse_bracket(text[1:-1].strip(), number))
                last_line = None
                continue

            match = DIALOGUE_LINE.match(text)
            if match:
                name, mods, words = match.group(1).strip(), match.group(2), match.group(3).strip()
                key = name.lower()
                if key not in cast and key in SETTINGS and not mods:
                    _apply_setting(script, key, words, number)
                    last_line = None
                    continue
                if key not in cast:
                    raise OptionError(_unknown_speaker_message(name, cast))
                if not words:
                    raise OptionError(f"{name} has nothing to say on this line. Put the words after the colon.")
                options = parse_options(mods) if mods else Options()
                last_line = Line(key, words, options, number)
                script.events.append(last_line)
                continue

            if last_line is not None:
                # A line straight after dialogue continues what was being said.
                last_line.text += " " + text
                continue
            raise OptionError(
                "I don't know who says this. Start the line with a character's name and a colon, "
                "like  Narrator: Once upon a time.  Sounds and music go in square brackets, like  [sound: knock]."
            )
        except OptionError as e:
            problem(number, str(e))

    if not cast:
        problems.append(ScriptProblem(0, "", "The script has no cast. Add a line such as  Narrator = Ryan  to choose a voice."))
    elif not any(isinstance(e, Line) for e in script.events) and not problems:
        problems.append(ScriptProblem(0, "", "Nobody says anything yet. Add a line such as  Narrator: Hello."))

    if problems:
        raise ScriptErrors(problems)
    return script


def _strip_note(raw):
    text = raw.strip()
    if text.startswith("#") or text.startswith("//"):
        return ""
    return text


def _unknown_speaker_message(name, cast):
    names = [c.name for c in cast.values()]
    close = difflib.get_close_matches(name.lower(), list(cast), n=1, cutoff=0.6)
    message = f'"{name}" is not in the cast.'
    if close:
        return message + f" Did you mean {cast[close[0]].name}?"
    if names:
        message += " The cast is: " + ", ".join(names) + "."
    return message + f" To add them, write a line such as  {name} = Jenny"


def _apply_setting(script, key, value, number):
    if key == "title":
        script.title = value or script.title
    elif key in ("gap", "ending"):
        match = SECONDS.match(value)
        if not match:
            raise OptionError(f"{key.title()} should be a number of seconds, like  {key.title()}: 0.5")
        setattr(script, key, float(match.group(1)))
    elif key == "format":
        words = re.split(r"[\s,]+|\band\b", value.lower().replace(".", " "))
        formats = [w for w in words if w]
        if "all" in formats:
            formats = ["mp3", "ogg", "wav"]
        if not formats or any(f not in ("mp3", "ogg", "wav") for f in formats):
            raise OptionError("Format can be mp3, ogg, wav, or all. You can list more than one, like  Format: mp3, ogg")
        script.formats = list(dict.fromkeys(formats))
    elif key == "scene":
        script.events.append(Scene(value, number))
    # cast, note, author: headings or information only.


def _parse_bracket(inner, number):
    lower = inner.lower()

    # [pause 2]  [pause: 2 seconds]  [silence 1]  [wait 3]
    for word in ("pause", "silence", "wait"):
        if lower.startswith(word):
            rest = lower[len(word):].strip()
            match = SECONDS.match(rest)
            if not rest:
                return Pause(1.0, number)
            if not match:
                raise OptionError(f"Write the pause as a number of seconds, like  [{word} 2]")
            return Pause(float(match.group(1)), number)

    # [stop music]  [stop all, fade out 3]  [stop rain]
    if lower.startswith("stop"):
        parts = [p.strip() for p in lower[4:].lstrip(" :").split(",")]
        target = parts[0] or "all"
        if target in ("everything", "all sounds", "all music"):
            target = "all"
        target = AUDIO_CHANNELS.get(target, target)
        fade = None
        if len(parts) > 1:
            opts = parse_options(",".join(parts[1:]))
            fade = opts.fade_out
        return Stop(target, fade, number)

    # [scene: The Cave]
    if lower.startswith("scene"):
        return Scene(inner[5:].lstrip(" :"), number)

    if ":" not in inner:
        raise OptionError(
            "I don't understand this. Square brackets can hold  [sound: name],  [music: name],  "
            "[ambience: name],  [pause 2]  or  [stop music]."
        )
    kind, rest = inner.split(":", 1)
    kind = kind.strip().lower()
    parts = rest.split(",", 1)
    name = parts[0].strip()
    if not name:
        raise OptionError(f"Put the name of a sound after  {kind}:")
    options = parse_options(parts[1]) if len(parts) > 1 else Options()

    if kind in SOUND_WORDS:
        if options.loop:
            # A looping sound keeps going like music, until [stop name].
            return StartChannel(Path(name).stem.lower(), name, options, number)
        return Sound(name, options, number)
    if kind in AUDIO_CHANNELS:
        # Music and ambience repeat until stopped, unless the script says "once".
        options.loop = not options.once
        return StartChannel(AUDIO_CHANNELS[kind], name, options, number)
    raise OptionError(
        f'I don\'t know "{kind}". Use sound, music, ambience or background before the colon.'
    )
