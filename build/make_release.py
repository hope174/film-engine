"""Build Film Maker.exe and pack it, with the guides, into a zip for a GitHub release.

    python build/make_release.py 1.0.0

Run it with a Python that has requirements.txt and pyinstaller installed.
The zip is written to %TEMP%\film-maker-build\dist\Film-Maker-<version>-windows.zip.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
# Outside OneDrive, which locks files while it syncs them.
OUT = Path(tempfile.gettempdir()) / "film-maker-build"
DIST = OUT / "dist"
WORK = OUT / "work"

# Copied next to Film Maker.exe, keeping the same folder layout.
FILES = [
    "Syntax.txt",
    "Script guide.txt",
    "sound-folders.txt",
    "sounds/Put shared sounds here.txt",
    "examples/the-lighthouse/script.txt",
]


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "dev"
    shutil.rmtree(DIST, ignore_errors=True)
    shutil.rmtree(WORK, ignore_errors=True)
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "Film Maker",
        "--distpath", str(DIST), "--workpath", str(WORK), "--specpath", str(WORK),
        "--add-data", f"{ROOT / 'filmengine' / 'template_script.txt'};filmengine",
        "--collect-data", "edge_tts", "--collect-data", "certifi",
        str(ROOT / "Film Maker.pyw"),
    ], check=True)

    app = DIST / "Film Maker"
    for name in FILES:
        target = app / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    shutil.copy2(BUILD / "Read me first.txt", app / "Read me first.txt")
    (app / "films").mkdir(exist_ok=True)

    zip_path = shutil.make_archive(str(DIST / f"Film-Maker-{version}-windows"), "zip", DIST, "Film Maker")
    print(f"Made {zip_path}")


if __name__ == "__main__":
    main()
