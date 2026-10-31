"""Command line for the film engine. The .bat files in the films folder call this.

    python -m filmengine make <film>        make the audio file for a film
    python -m filmengine check <film>       look for mistakes without making anything
    python -m filmengine new <name>         start a new film from the template
    python -m filmengine voices [words]     list voices, e.g. "british female"
    python -m filmengine try <voice> [text] [--style "whisper, echo"]
    python -m filmengine sounds             list built-in and shared sounds
    python -m filmengine words              list every style, effect and option word
"""

import argparse
import difflib
import os
import sys
import time
import traceback
from pathlib import Path

from .errors import FilmError
from .paths import CACHE_DIR, FILMS_DIR, ROOT, SHARED_SOUNDS_DIR, TEMPLATE

ACCENTS = {"american": "en-US", "us": "en-US", "british": "en-GB", "english": "en-GB", "uk": "en-GB",
           "australian": "en-AU", "irish": "en-IE", "canadian": "en-CA", "indian": "en-IN",
           "scottish": "en-GB", "new zealand": "en-NZ", "kiwi": "en-NZ", "south african": "en-ZA"}


def find_script(name):
    if not name:
        raise FilmError("Tell me which film. For example:  Make a film.bat  the-lighthouse")
    given = Path(name.strip().strip('"'))
    if given.is_file():
        return given.resolve()
    if given.is_dir():
        return _script_in(given)
    folders = [f for f in FILMS_DIR.iterdir() if f.is_dir()] if FILMS_DIR.exists() else []
    for folder in folders:
        if folder.name.lower() == name.strip().lower():
            return _script_in(folder)
    names = [f.name for f in folders]
    close = difflib.get_close_matches(name.lower(), [n.lower() for n in names], n=1, cutoff=0.5)
    message = f'There is no film called "{name}" in the films folder.'
    if close:
        message += f" Did you mean {close[0]}?"
    elif names:
        message += " The films are: " + ", ".join(names) + "."
    raise FilmError(message)


def _script_in(folder):
    folder = Path(folder).resolve()
    if (folder / "script.txt").exists():
        return folder / "script.txt"
    texts = [f for f in folder.glob("*.txt") if "timeline" not in f.name.lower() and f.name.lower() != "lines.txt"]
    if len(texts) == 1:
        return texts[0]
    raise FilmError(f"The folder {folder.name} needs a file called script.txt with the film's script in it.")


def list_films():
    if not FILMS_DIR.exists():
        return []
    return sorted(f.name for f in FILMS_DIR.iterdir() if f.is_dir())


def cmd_make(args):
    from . import render
    from .script import parse_script

    path = find_script(args.film)
    print(f"Reading {path.parent.name}/{path.name}")
    script = parse_script(path)
    formats = ["wav"] if args.wav else script.formats
    base = path.parent / "output" / render.safe_filename(script.title)
    started = time.time()
    written, length = render.render(script, base, formats)
    minutes, seconds = divmod(int(round(length)), 60)
    print()
    print(f"Done. The film is {minutes} minutes {seconds} seconds long.")
    for file in written:
        print(f"Saved as: {file}")
    print(f"A list of what happens when is in: output/{base.name} - timeline.txt")
    print("Every line with its id is in lines.txt, next to the script.")
    print(f"(That took {time.time() - started:.0f} seconds.)")
    if args.play:
        os.startfile(written[0])
    elif args.ask_play:
        try:
            answer = input("\nDo you want to listen to it now? Type y and press Enter, or just press Enter to skip: ")
        except EOFError:
            answer = ""
        if answer.strip().lower().startswith("y"):
            os.startfile(written[0])


def cmd_check(args):
    from . import render
    from .script import Line, parse_script

    path = find_script(args.film)
    script = parse_script(path)
    render.check(script)
    lines = sum(isinstance(e, Line) for e in script.events)
    print(f'"{script.title}" looks good. {len(script.cast)} characters and {lines} spoken lines. No problems found.')


def cmd_new(args):
    name = " ".join(args.name).strip()
    if not name:
        raise FilmError("Give the new film a name, for example:  New film.bat  the-haunted-house")
    folder_name = "-".join(name.lower().split())
    folder = FILMS_DIR / folder_name
    if folder.exists():
        raise FilmError(f"There is already a film called {folder_name}. Pick another name.")
    (folder / "sounds").mkdir(parents=True)
    (folder / "sounds" / "put this film's sound files here.txt").write_text(
        "Put sound files for this film in this folder (wav, mp3, ogg or flac).\n"
        "In the script, use the file name without the ending, for example [sound: door-slam]\n",
        encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8").replace("{title}", name.title())
    (folder / "script.txt").write_text(template, encoding="utf-8")
    print(f"Made a new film folder: films/{folder_name}")
    print(f"Open films/{folder_name}/script.txt to write the script.")
    if args.open:
        os.startfile(folder / "script.txt")


def cmd_voices(args):
    from . import voices

    words = " ".join(args.words).lower()
    all_v = voices.all_voices(refresh=args.refresh)
    chosen = all_v
    if "all" not in words.split():
        locales = {loc for word, loc in ACCENTS.items() if word in words}
        codes = {w for w in words.split() if "-" in w}
        if codes:
            chosen = [v for v in chosen if any(v["locale"].lower().startswith(c.lower()) for c in codes)]
        elif locales:
            chosen = [v for v in chosen if v["locale"] in locales]
        else:
            chosen = [v for v in chosen if v["locale"].startswith("en-")]
        if "female" in words or "woman" in words:
            chosen = [v for v in chosen if v["gender"].lower() == "female"]
        elif "male" in words or "man" in words:
            chosen = [v for v in chosen if v["gender"].lower() == "male"]
    chosen = sorted(chosen, key=lambda v: (v["locale"], v["name"]))
    print(f"{len(chosen)} voices. In a script you can use the full name or the short name.")
    print('Try one with:  Try a voice.bat  then type the short name.\n')
    for v in chosen:
        print(voices.describe(v))


def cmd_try(args):
    from . import audio, effects, tts, voices
    from .script import OptionError, parse_options

    voice = voices.resolve(args.voice)
    text = " ".join(args.text) or f"Hello. My name is {voices.short_name(voice)}. This is how I sound."
    try:
        opts = parse_options(args.style) if args.style else parse_options("")
    except OptionError as e:
        raise FilmError(str(e))
    path = tts.synthesize([(text, voice, opts.rate, opts.pitch)])[(text, voice, opts.rate, opts.pitch)]
    clip = effects.apply(audio.load(path), opts.effects)
    clip = effects.position(clip, opts.angle, opts.distance, opts.movement) * opts.gain
    written = audio.save(clip, CACHE_DIR / "try-a-voice.mp3")
    print(f"Playing {voice}.")
    os.startfile(written)


def cmd_sounds(args):
    from . import audio, builtin_sounds

    print("Built-in sounds (you can use these without any files):")
    for name, (_, description) in builtin_sounds.BUILTIN.items():
        print(f"  {name}: {description}")
    files = sorted(f for f in SHARED_SOUNDS_DIR.rglob("*") if f.suffix.lower() in audio.AUDIO_EXTENSIONS) \
        if SHARED_SOUNDS_DIR.exists() else []
    print(f"\nSound files in the shared sounds folder: {len(files)}")
    for f in files:
        print(f"  {f.stem}   ({f.relative_to(SHARED_SOUNDS_DIR)})")


def cmd_words(args):
    from . import builtin_sounds
    from .effects import EFFECTS
    from .script import DISTANCE_WORDS, FLAGS, MOVEMENTS, POSITION_WORDS, SPEECH_STYLES, SYNONYMS

    groups = [
        ("Speaking styles (voices only)", SPEECH_STYLES),
        # Some effects are reached through a speaking style of the same idea, so list them once.
        ("Effects (voices and sounds)", [e for e in EFFECTS if e not in SPEECH_STYLES and e not in SYNONYMS
                                         and e != "drive"]),
        ("Positions", POSITION_WORDS),
        ("Distances", DISTANCE_WORDS),
        ("Movements", MOVEMENTS),
        ("Sound and music options", sorted(FLAGS | {"no duck"})),
        ("Settings with a number", ["fade in 2", "fade out 2", "delay 1.5", "skip 2", "length 3",
                                    "volume 50", "volume -6 db", "gain -6", "rate -10%", "pitch +5hz",
                                    "pan -50", "angle 120", "distance 3"]),
        ("Built-in sounds", builtin_sounds.BUILTIN),
    ]
    for title, words in groups:
        print(f"{title}:")
        print("  " + ", ".join(words))
        print()
    print("Other words that mean the same as one above:")
    for word, meaning in sorted(SYNONYMS.items()):
        print(f"  {word} means {meaning}")


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(prog="filmengine", description="Make audio films from scripts.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("make", help="make the audio file for a film")
    p.add_argument("film", nargs="?")
    p.add_argument("--wav", action="store_true", help="save as WAV instead of MP3")
    p.add_argument("--play", action="store_true", help="play it when done")
    p.add_argument("--ask-play", action="store_true", help="ask whether to play it when done")
    p.set_defaults(func=cmd_make)

    p = sub.add_parser("check", help="look for mistakes in a script")
    p.add_argument("film", nargs="?")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("new", help="start a new film")
    p.add_argument("name", nargs="*")
    p.add_argument("--open", action="store_true", help="open the new script in Notepad")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("voices", help="list voices")
    p.add_argument("words", nargs="*")
    p.add_argument("--refresh", action="store_true", help="download the voice list again")
    p.set_defaults(func=cmd_voices)

    p = sub.add_parser("try", help="hear a voice")
    p.add_argument("voice")
    p.add_argument("text", nargs="*")
    p.add_argument("--style", default="", help='for example "whisper, echo"')
    p.set_defaults(func=cmd_try)

    p = sub.add_parser("films", help="list the films")
    p.set_defaults(func=lambda a: print("\n".join(list_films()) or "There are no films yet."))

    p = sub.add_parser("sounds", help="list sounds")
    p.set_defaults(func=cmd_sounds)

    p = sub.add_parser("words", help="list every word a script can use in brackets")
    p.set_defaults(func=cmd_words)

    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except FilmError as e:
        print()
        print(e)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.")
        return 1
    except Exception:
        CACHE_DIR.mkdir(exist_ok=True)
        details = CACHE_DIR / "last-error.txt"
        details.write_text(traceback.format_exc(), encoding="utf-8")
        print("\nSomething went wrong inside the engine. This is not a mistake in your script.")
        print(f"Please send the file {details.relative_to(ROOT)} to the person who looks after the engine.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
