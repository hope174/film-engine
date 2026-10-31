"""Double-click to open Film Maker, the window for writing and making films."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def tell(message):
    # No console here, so show problems in a standard Windows message box.
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, message, "Film Maker", 0x40)


if len(sys.argv) > 1:
    # Commands such as "make the-lighthouse" run the engine without the window,
    # like run.bat. Film Maker.exe has no console, so what it says goes to a file.
    from filmengine.__main__ import main as run_command
    from filmengine.paths import CACHE_DIR
    if sys.stdout is None:
        CACHE_DIR.mkdir(exist_ok=True)
        sys.stdout = sys.stderr = open(CACHE_DIR / "last-run.txt", "w", encoding="utf-8")
    sys.exit(run_command(sys.argv[1:]))

try:
    from filmengine.app import main
except ImportError:
    tell("Film Maker is not set up yet. Double-click Setup.bat first, then try again.")
    sys.exit(1)

sys.exit(main())
