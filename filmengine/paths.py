"""Where things live in the films folder."""

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # Built as Film Maker.exe: films and sounds sit next to the program,
    # and the engine's own files are unpacked beside its code.
    ROOT = Path(sys.executable).resolve().parent
    ENGINE_DIR = Path(sys._MEIPASS) / "filmengine"
else:
    ROOT = Path(__file__).resolve().parent.parent
    ENGINE_DIR = ROOT / "filmengine"
FILMS_DIR = ROOT / "films"
SHARED_SOUNDS_DIR = ROOT / "sounds"
SOUND_FOLDERS_FILE = ROOT / "sound-folders.txt"
CACHE_DIR = ROOT / ".cache"
TTS_CACHE_DIR = CACHE_DIR / "speech"
TEMPLATE = ENGINE_DIR / "template_script.txt"
