# Film Engine

Turns plain-text scripts into audio films: Edge TTS neural voices (or Windows SAPI voices) for the
characters, plus sound effects, looping music and ambience, voice effects and positional audio.

The person making films should start with `Read me first.txt` and `Script guide.txt`, and use the
`.bat` files. This file is for whoever maintains the engine.

## Setup

`Setup.bat` installs Python 3.12 (via winget, if missing), the packages in `requirements.txt`,
and ffmpeg. ffmpeg is optional: without it, MP3 output falls back to WAV and only
wav/mp3/flac/ogg can be read (via miniaudio).

## Command line

All `.bat` files call `filmengine\run.bat`, which finds Python and runs `python -m filmengine`:

    python -m filmengine make <film> [--wav] [--play] [--ask-play]
    python -m filmengine check <film>
    python -m filmengine new <name> [--open]
    python -m filmengine voices [british female | en-AU | all] [--refresh]
    python -m filmengine try <voice> [text...] [--style "whisper, echo"]
    python -m filmengine films
    python -m filmengine sounds

`<film>` is a folder name under `films/`, a folder path, or a script path.

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

Scripts, sounds and recordings are tracked. `.cache/` and `films/*/output/` are ignored, since
renders are reproducible and large. `Save my work.bat` runs `git add -A` and a dated commit.
There is no remote yet; add one for an off-machine backup.
