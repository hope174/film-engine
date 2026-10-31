# Film Engine

Turns plain-text scripts into audio films: Edge TTS neural voices (or Windows SAPI voices) for the
characters, plus sound effects, looping music and ambience, voice effects and positional audio.

The person making films should start with `Read me first.txt`, `Syntax.txt` and `Script guide.txt`,
and use `Film Maker.bat` (the window) or the other `.bat` files. AI agents making films follow `AGENTS.md` (`CLAUDE.md` imports it).
This file is for whoever maintains the engine.

## Setup

`Setup.bat` installs Python 3.12 (via winget, if missing), the packages in `requirements.txt`,
and ffmpeg. ffmpeg is optional: without it, MP3 and OGG output are written by libsndfile (through
soundfile), and only wav/mp3/flac/ogg can be read (via miniaudio).

## Film Maker (the window)

`filmengine/app.py` is a wxPython window: a film list, a script editor, a messages box, and menus
for inserting characters, lines, sounds, pauses, stops and scenes, plus make, check and play.
It is built for screen reader users. It only uses native controls (ListBox, TextCtrl, Choice and the
standard dialogs), puts a mnemonic label before every control, gives every action a menu item and
a shortcut, and reports results in dialogs. Making a film runs on a worker thread, and its
progress goes to the messages box through `wx.CallAfter`. When a check fails, the cursor moves to
the first problem line. Launch it with `Film Maker.pyw`, which opens through the pyw launcher, or `Film Maker.bat`,
which finds Python itself. The speed, pitch and volume sliders write `rate`, `pitch` and `volume`
options, and `split_settings` reads them back so a cast line can be edited.

`filmengine/films.py` has the operations the app and the command line share: find, create,
check and make a film, and make a voice sample.

## Command line

All `.bat` files call `filmengine\run.bat`, which finds Python and runs `python -m filmengine`:

    python -m filmengine make <film> [--wav] [--play] [--ask-play]
    python -m filmengine check <film>
    python -m filmengine new <name> [--open]
    python -m filmengine voices [british female | en-AU | all] [--refresh]
    python -m filmengine try <voice> [text...] [--style "whisper, echo"]
    python -m filmengine films
    python -m filmengine sounds
    python -m filmengine words
    python -m filmengine.check_syntax_file

`<film>` is a folder name under `films/`, a folder path, or a script path. Exit codes: 0 OK,
1 a problem the user can fix (script, missing film, network), 2 an engine bug.

`words` prints every accepted option word straight from the parser's tables. `check_syntax_file`
runs every labelled example in `Syntax.txt` through the parser and `render.check`, and fails if any
example doesn't behave as labelled. Run it after any change to the script format.

## How it works

1. `script.py` parses the script in two passes (cast lines first, so reserved words such as
   `Title:` can still be character names) into events: `Line`, `Sound`, `StartChannel`, `Stop`,
   `Pause`, `Scene`. All problems are collected and reported together with line numbers.
2. `render.py` resolves voices (`voices.py`) and sounds (`SoundFinder`), synthesises every line
   (`tts.py`, cached in `.cache/speech/` by voice, text, rate and pitch), then walks the events
   with a time cursor. Lines and sounds advance the cursor; `nowait` and `overlap` do not.
   Music, ambience and background are named channels that loop until stopped or the end.
3. The mix is summed in float32 at 44.1 kHz stereo, music is ducked under speech, and the result
   is peak-normalised to about -1 dBFS and written by `audio.save`.

Each render also writes `output/<title> - timeline.txt` and `lines.txt` (line ids). A file at
`films/<film>/voice/L012.wav` replaces generated line L012, the convention from the earlier
"bat film" project.

Effects are in `effects.py` (`EFFECTS` maps script words to functions; `position` handles angle,
distance and movement). Speaking styles and synonyms are tables at the top of `script.py`.
Built-in procedural sounds are in `builtin_sounds.py`.

## Git

`films/` is ignored: the repository is public and the films are private, so they stay on this
computer and in OneDrive. `examples/the-lighthouse` is a tracked example film. `.cache/`, every
`output/` folder and every `lines.txt` are ignored, since they can be made again. `Save my work.bat` runs `git add -A` and a dated commit.
The remote is https://github.com/hope174/film-engine (public).

## Releases

`build/make_release.py <version>` builds `Film Maker.exe` with PyInstaller (one folder, no console)
and zips it with `build/Read me first.txt` (the read-me for downloaders), `Syntax.txt`,
`Script guide.txt`, `sound-folders.txt`, the example script and empty `films` and `sounds` folders.
Run it with a Python that has `requirements.txt` and `pyinstaller` installed, ideally a venv.
The output goes to `%TEMP%\film-maker-build`, because OneDrive locks files in the build folders.
Upload the zip with `gh release create v<version> <zip>`.

When frozen, `paths.py` puts `ROOT` next to the exe and reads `template_script.txt` from the bundle.
`Film Maker.exe <command>` (and `Film Maker.pyw <command>`) runs the same commands as `run.bat`
without the window. With no console, the output goes to `.cache/last-run.txt`.
