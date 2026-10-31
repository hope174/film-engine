"""Double-click to open Film Maker, the window for writing and making films."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def tell(message):
    # No console here, so show problems in a standard Windows message box.
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, message, "Film Maker", 0x40)


try:
    from filmengine.app import main
except ImportError:
    tell("Film Maker is not set up yet. Double-click Setup.bat first, then try again.")
    sys.exit(1)

sys.exit(main())
