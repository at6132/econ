"""Refactor helper: rewrite ``from realm.X import Y`` and ``import realm.X``.

Usage::

    python scripts/refactor_imports.py old1=new1 old2=new2 ...

Where each ``old=new`` is a module path remapping (no ``realm.`` prefix).
The script walks ``engine/realm/`` and ``engine/tests/`` and rewrites every
matching ``from realm.OLD ...``, ``import realm.OLD``, and ``realm.OLD.X``
reference to use ``realm.NEW`` instead.

Supports nested paths::

    old=ledger              new=core.ledger
    old=ids                 new=core.ids
    old=genesis_pricing     new=economy.pricing      # rename + folder

Reports the count of files modified and total replacements made.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOTS = ("realm", "tests")


def _walk_py_files(roots: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for r in roots:
        for dirpath, _dirs, files in os.walk(r):
            if "__pycache__" in dirpath:
                continue
            for f in files:
                if f.endswith(".py"):
                    out.append(Path(dirpath) / f)
    return out


def _build_patterns(mappings: dict[str, str]) -> list[tuple[re.Pattern[str], str, str]]:
    """Return list of (compiled_regex, replacement, description) tuples.

    Three pattern shapes are rewritten:
      1. ``from realm.OLD import ...``  (also ``from realm.OLD.SUB import``)
      2. ``import realm.OLD``           (also ``import realm.OLD.SUB``)
      3. ``realm.OLD.something``        (qualified usage in code)
    """
    patterns: list[tuple[re.Pattern[str], str, str]] = []
    # Sort by length desc so e.g. genesis_pricing matches before genesis
    keys = sorted(mappings.keys(), key=len, reverse=True)
    for old in keys:
        new = mappings[old]
        # word boundary on either side so ``realm.ledger`` does not match
        # ``realm.ledger_x``
        old_esc = re.escape(old)
        # Case 1: ``from realm.OLD`` followed by ``.``, whitespace, or end
        p1 = re.compile(rf"\bfrom realm\.{old_esc}(?=[\s.])")
        patterns.append((p1, f"from realm.{new}", f"from realm.{old}"))
        # Case 2: ``import realm.OLD`` followed by ``.``, whitespace, or end
        p2 = re.compile(rf"\bimport realm\.{old_esc}(?=[\s.\n,]|$)")
        patterns.append((p2, f"import realm.{new}", f"import realm.{old}"))
        # Case 3: ``realm.OLD.something`` qualified attribute use (e.g. type hint
        # strings or ``realm.ledger.Ledger``). Avoid matching ``realm.OLDX``.
        p3 = re.compile(rf"\brealm\.{old_esc}(?=\.)")
        patterns.append((p3, f"realm.{new}", f"realm.{old}"))
    return patterns


def rewrite(mappings: dict[str, str], roots: tuple[str, ...] = ROOTS) -> tuple[int, int]:
    patterns = _build_patterns(mappings)
    files_changed = 0
    total_subs = 0
    for path in _walk_py_files(roots):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        new_text = text
        local_subs = 0
        for pattern, replacement, _desc in patterns:
            new_text, n = pattern.subn(replacement, new_text)
            local_subs += n
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            files_changed += 1
            total_subs += local_subs
    return files_changed, total_subs


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    mappings: dict[str, str] = {}
    for arg in argv:
        if "=" not in arg:
            print(f"bad mapping: {arg!r} (expected old=new)", file=sys.stderr)
            return 2
        old, new = arg.split("=", 1)
        mappings[old.strip()] = new.strip()
    files_changed, subs = rewrite(mappings)
    pretty = ", ".join(f"{k}->{v}" for k, v in mappings.items())
    print(f"rewrote {subs} occurrences across {files_changed} files: {pretty}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
