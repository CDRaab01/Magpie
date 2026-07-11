#!/usr/bin/env python3
"""Fail if any source file contains UTF-8 mojibake (ROADMAP #13).

Twice this project shipped em-dashes written through cp1252, so a real UTF-8 em-dash (U+2014)
turned into a three-character byte soup on screen. That's invisible in review and only surfaces
in a screenshot. This guard scans tracked text source for the *mis-encoded* marker sequences --
not real UTF-8 punctuation, which is fine -- so the next corrupted write fails the build instead
of the eyeball.

The markers are written as unicode escapes so this file itself stays pure ASCII and never
false-positives on its own source.

Run from the repo root: `python scripts/check_encoding.py`.
"""

from __future__ import annotations

import pathlib
import sys

# Sequences that only appear when UTF-8 was decoded as cp1252 and re-encoded. The first is the
# shared prefix of the em-dash / smart-quote mojibake family (a-circumflex + euro sign); the
# "C3 .." pairs are accented mojibake (would-be e-acute / e-grave / n-tilde); U+FFFD is the
# replacement char for bytes that could not decode at all. Real UTF-8 punctuation contains none
# of these, so this is low-false-positive by design.
MARKERS = (
    chr(0x00E2) + chr(0x20AC),  # em-dash / smart-quote mangle (a-circumflex + euro)
    chr(0x00C3) + chr(0x00A2),  # accented-A + cent
    chr(0x00C3) + chr(0x00A9),  # e-acute mojibake
    chr(0x00C3) + chr(0x00A8),  # e-grave mojibake
    chr(0x00C3) + chr(0x00B1),  # n-tilde mojibake
    chr(0xFFFD),  # replacement character
)

SCAN_SUFFIXES = {".kt", ".kts", ".py", ".md", ".yml", ".yaml", ".json", ".toml"}
SKIP_DIRS = {".git", "build", ".gradle", "node_modules", "__pycache__", ".venv", "venv"}


def offending_files(root: pathlib.Path) -> list[tuple[pathlib.Path, int, str]]:
    hits: list[tuple[pathlib.Path, int, str]] = []
    for path in root.rglob("*"):
        if path.suffix not in SCAN_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            # A source file that isn't even valid UTF-8 is itself a failure.
            hits.append((path, 0, "not valid UTF-8"))
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for marker in MARKERS:
                if marker in line:
                    hits.append((path, lineno, marker.encode("unicode_escape").decode()))
                    break
    return hits


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    hits = offending_files(root)
    if not hits:
        print("encoding check: clean")
        return 0
    print("encoding check: mojibake found (UTF-8 written through cp1252?):", file=sys.stderr)
    for path, lineno, marker in hits:
        print(f"  {path.relative_to(root)}:{lineno}  contains {marker!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
