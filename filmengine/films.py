"""Finding, creating and making films. Shared by the command line and the app."""

import difflib
from pathlib import Path

from . import audio
from .errors import FilmError
from .paths import FILMS_DIR, TEMPLATE


def list_films():
    if not FILMS_DIR.exists():
        return []
    return sorted(f.name for f in FILMS_DIR.iterdir() if f.is_dir())


def find_script(name):
    """A film's script from its folder name, a folder path or a script path."""
    if not name:
        raise FilmError("Tell me which film. For example:  Make a film.bat  the-lighthouse")
    given = Path(name.strip().strip('"'))
    if given.is_file():
        return given.resolve()
    if given.is_dir():
        return script_in(given)
    for folder_name in list_films():
        if folder_name.lower() == name.strip().lower():
            return script_in(FILMS_DIR / folder_name)
    names = list_films()
    close = difflib.get_close_matches(name.lower(), [n.lower() for n in names], n=1, cutoff=0.5)
    message = f'There is no film called "{name}" in the films folder.'
    if close:
        message += f" Did you mean {close[0]}?"
    elif names:
        message += " The films are: " + ", ".join(names) + "."
    raise FilmError(message)


def script_in(folder):
    folder = Path(folder).resolve()
    if (folder / "script.txt").exists():
        return folder / "script.txt"
    texts = [f for f in folder.glob("*.txt") if "timeline" not in f.name.lower() and f.name.lower() != "lines.txt"]
    if len(texts) == 1:
        return texts[0]
    raise FilmError(f"The folder {folder.name} needs a file called script.txt with the film's script in it.")


def create_film(name):
    """Make a new film folder with a starter script. Returns the script's path."""
    name = name.strip()
    if not name:
        raise FilmError("Give the new film a name, for example: the haunted house")
    folder_name = "-".join(name.lower().split())
    if any(c in folder_name for c in '<>:"/\\|?*'):
        raise FilmError('A film name can\'t have any of these in it:  < > : " / \\ | ? *')
    folder = FILMS_DIR / folder_name
    if folder.exists():
        raise FilmError(f"There is already a film called {folder_name}. Pick another name.")
    (folder / "sounds").mkdir(parents=True)
    (folder / "sounds" / "put this film's sound files here.txt").write_text(
        "Put sound files for this film in this folder (wav, mp3, ogg or flac).\n"
        "In the script, use the file name without the ending, for example [sound: door-slam]\n",
        encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8").replace("{title}", name.title())
    script = folder / "script.txt"
    script.write_text(template, encoding="utf-8")
    return script


def make_film(script_path, say=print, wav=False):
    """Read and make a film. Returns (written files, length in seconds)."""
    from . import render
    from .script import parse_script

    script = parse_script(script_path)
    formats = ["wav"] if wav else script.formats
    base = Path(script_path).parent / "output" / render.safe_filename(script.title)
    return render.render(script, base, formats, say=say)


def check_film(script_path):
    """Look for problems. Returns the parsed script. Raises ScriptErrors."""
    from . import render
    from .script import parse_script

    script = parse_script(script_path)
    render.check(script)
    return script


def voice_sample(voice, text="", style=""):
    """Make a short sample of a voice, with optional styles. Returns the file's path."""
    from . import effects, tts, voices
    from .paths import CACHE_DIR
    from .script import OptionError, parse_options

    full = voices.resolve(voice)
    text = text.strip() or f"Hello. My name is {voices.short_name(full)}. This is how I sound."
    try:
        opts = parse_options(style)
    except OptionError as e:
        raise FilmError(str(e))
    request = (text, full, opts.rate, opts.pitch)
    clip = effects.apply(audio.load(tts.synthesize([request])[request]), opts.effects)
    clip = effects.position(clip, opts.angle, opts.distance, opts.movement) * opts.gain
    return audio.save(clip, CACHE_DIR / "try-a-voice.mp3")


def finished_files(folder):
    """The film's finished audio files, newest first."""
    output = Path(folder) / "output"
    if not output.is_dir():
        return []
    files = [f for f in output.iterdir() if f.suffix.lower() in audio.AUDIO_EXTENSIONS]
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)
