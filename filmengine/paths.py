"""Where things live in the films folder."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILMS_DIR = ROOT / "films"
SHARED_SOUNDS_DIR = ROOT / "sounds"
SOUND_FOLDERS_FILE = ROOT / "sound-folders.txt"
CACHE_DIR = ROOT / ".cache"
TTS_CACHE_DIR = CACHE_DIR / "speech"
TEMPLATE = ROOT / "filmengine" / "template_script.txt"
