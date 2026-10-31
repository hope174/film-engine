"""Checks that every example in Syntax.txt behaves the way the file says.

    python -m filmengine.check_syntax_file

"Right:" and "Example:" blocks must work. "Wrong:" blocks must be reported as
problems. "Wrong, and the engine will not warn you:" blocks must not be.
Run this after changing the script format or Syntax.txt.
"""

import sys
import tempfile
from pathlib import Path

from . import render
from .errors import FilmError
from .paths import ROOT
from .script import CAST_LINE, parse_script

BASE_CAST = {"narrator": "Narrator = Ryan", "mara": "Mara = Sonia", "keeper": "Keeper = Guy"}
LABELS = {"right:": "works", "example:": "works", "wrong:": "fails", "wrong, and the engine will not warn you:": "quiet"}


def blocks(text):
    label, lines = None, []
    for raw in text.splitlines():
        if raw.startswith("    ") or (not raw.strip() and lines):
            if label:
                lines.append(raw[4:])
            continue
        if label and lines:
            yield label, lines
        label, lines = LABELS.get(raw.strip().lower()), []
    if label and lines:
        yield label, lines


def outcome(lines, folder):
    """Returns None if the lines work, or the problem message."""
    own = [l for l in lines if l.strip() and not l.strip().startswith(("#", "(")) and l.lstrip() == l]
    cast_names = {CAST_LINE.match(l).group(1).strip().lower() for l in own if CAST_LINE.match(l) and not l.startswith("[")}
    body = [l for l in lines if not l.strip().startswith("(")]  # drop the explanations
    # Fill in the usual cast and one spoken line, so a block can show just one kind of line.
    script = [c for k, c in BASE_CAST.items() if k not in cast_names] + body + ["", "Narrator: Test."]
    path = folder / "script.txt"
    path.write_text("\n".join(script) + "\n", encoding="utf-8")
    try:
        render.check(parse_script(path))
        return None
    except FilmError as e:
        return str(e)


def main():
    text = (ROOT / "Syntax.txt").read_text(encoding="utf-8")
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for label, lines in blocks(text):
            problem = outcome(lines, Path(tmp))
            ok = (problem is None) if label in ("works", "quiet") else (problem is not None)
            if not ok:
                failures += 1
                expected = "to work" if label != "fails" else "to be reported as a problem"
                print(f"Expected {expected}:\n  " + "\n  ".join(lines))
                if problem:
                    print("  Got: " + problem.replace("\n", "\n  "))
                print()
    print("Syntax.txt examples all behave as described." if not failures else f"{failures} examples are wrong.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
