# Instructions for AI agents

This folder makes audio-only films from plain-text scripts. If you are asked to make, write or
change a film, follow this file. You should not need to read or change the engine code.

The person who uses this folder is not a programmer. When you report back, use plain words:
say what the film is called, how long it is, and where the file is. Don't paste code or tracebacks.

## Make a film in five steps

Run every command from this folder (the one holding this file). In PowerShell, start the command
with `& .\filmengine\run.bat`. In cmd, use `filmengine\run.bat`. From a POSIX shell, use
`cmd //c "filmengine\run.bat <command>"`. run.bat finds Python on its own; Python is not on PATH.

1. Create the folder: `filmengine\run.bat new <film name>`. This makes `films/<film-name>/` with
   a starter `script.txt` and a `sounds/` folder. Never pass `--open`. It opens Notepad on the
   user's screen. You can also create `films/<film-name>/script.txt` yourself.
2. Write `script.txt`. `Syntax.txt` shows every kind of line with right and wrong examples;
   read it first. `Script guide.txt` explains each option in more detail.
3. Check it: `filmengine\run.bat check <film-name>`. Repeat until it reports no problems. Exit code 0
   means OK, 1 means problems in the script (the output gives line numbers and suggestions),
   2 means an engine bug (details in `.cache/last-error.txt`; report it, don't work around it).
4. Make it: `filmengine\run.bat make <film-name>`. Never pass `--play` or `--ask-play`. They play
   audio on the user's speakers or wait for keyboard input. The film is written to
   `films/<film-name>/output/<Title>.mp3`.
5. Verify: you can't listen to the film, so read `output/<Title> - timeline.txt`. It lists the
   time of every line and sound. Check the order and the gaps, and that the total length is
   sensible. Don't commit films: `films/` is ignored on purpose, because the repository is
   public and the films are private. They are kept on this computer and in OneDrive.

## Look things up rather than guessing

- `filmengine\run.bat words` prints every style, effect, position and option word the parser
  accepts, plus the built-in sound names. Words outside this list are errors.
- `filmengine\run.bat voices [british female | american male | en-AU | all]` lists voices.
- `filmengine\run.bat sounds` lists built-in sounds and the files in the shared `sounds/` folder.
  Sound files can also be in `films/<film>/sounds/` or a folder listed in `sound-folders.txt`.
  Never name a sound file that doesn't exist. Use a built-in sound, or tell the user which
  sound files they would need to add.
- Don't use `try`. It plays audio aloud.
- Don't open `Film Maker.bat` or `filmengine.app`. That is the window for people, and it takes
  keyboard focus from the user. Use the commands above instead.

These English voices are known to exist and sound distinct. Use the short name in the cast:
- American men: Andrew, Brian, Guy, Christopher, Eric, Roger, Steffan.
- American women: Ava, Emma, Jenny, Aria, Michelle. Ana sounds like a child.
- British: Ryan and Thomas (men), Sonia and Libby (women), and Maisie (a girl).
- Other accents: Connor and Emily (Irish), Natasha (Australian), Liam and Clara (Canadian).
- Windows voices, which work offline and sound like a screen reader: Microsoft David, Microsoft Zira.

## Writing a good audio film

- Nothing can be seen, so a Narrator or Describer character carries anything visual: who is in the
  room, what they are doing, where they are. Keep these lines short and put them just before the
  moment they describe.
- Give every character a clearly different voice: mix men and women, accents, and pitch
  (`low`, `high`). Two similar voices talking to each other are hard to follow.
- Short spoken lines sound more natural than long ones. Split long speeches into several lines.
- Start each scene with `Scene: <name>` and an `[ambience: ...]` that sets the place. Stop or replace
  the ambience when the place changes.
- Keep music quiet: about `volume 40` for music under speech. Music ducks under speech by itself.
- Use `nowait` on a sound that should happen while someone is talking, such as thunder under a
  line. Leave it out when the story should wait for the sound, such as a knock before someone answers.
- Keep each character in one position (`left`, `behind`, and so on) for a whole scene, so the
  listener can tell where everyone is.
- Use `[pause 1]` to `[pause 3]` between scenes, and end with `[stop all, fade out 4]`.
- Spoken text is read literally. Write numbers, abbreviations and symbols the way they should be
  said, such as "Doctor Hale" rather than "Dr. Hale". Never put styles after the colon.

## Template for a new script

```
# <one line about the film>
Title: <Title>

Narrator = Ryan
<Character> = <Voice>[, styles]

Scene: <Place>
[ambience: <sound>, fade in 2]
Narrator: <What the listener needs to picture.>
<Character>: <Line.>
[sound: <sound>]
<Character> (<style>): <Line.>

[pause 2]
[stop all, fade out 4]
```

## If you change the engine

Only change the engine if you are asked to. Engine code is in `filmengine/`, and `README.md` explains how it works.
After changing the script format, `Syntax.txt` or `Script guide.txt`, run
`python -m filmengine.check_syntax_file` through the same Python. Every example in `Syntax.txt` must
behave as labelled. Then make `examples/the-lighthouse` to check that nothing broke (`make` takes
a folder path). Its output folder is ignored by git.
