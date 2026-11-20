#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Every first-party source file must declare an SPDX licence identifier."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._files import resolve  # noqa: E402

CODE_SUFFIXES = {".py", ".sh", ".yml", ".yaml", ".js", ".css", ".html", ".sv", ".v", ".sby"}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache"}
# Generated or third-party content with its own attribution rules.
SKIP_NAMES = {".gitignore", ".gitattributes", ".editorconfig"}


def needs_header(path: Path) -> bool:
    if path.name in SKIP_NAMES:
        return False
    if path.suffix.lower() not in CODE_SUFFIXES:
        return False
    # Repository configuration is not redistributed code: GitHub renders it and a
    # licence header is noise. Everything that ships for a user needs a header.
    if path.as_posix().replace("\\", "/").startswith(".github/"):
        return False
    return True


def main(argv: list[str]) -> int:
    files = [p for p in resolve(argv[1:]) if not any(part in SKIP_DIRS for part in p.parts)]

    missing = []
    for path in files:
        if not needs_header(path):
            continue
        try:
            head = path.read_text(encoding="utf-8", errors="ignore")[:800]
        except OSError:
            continue
        if "SPDX-License-Identifier" not in head:
            missing.append(path.as_posix())

    if missing:
        print("missing SPDX headers:", file=sys.stderr)
        for item in missing:
            print(f"  {item}", file=sys.stderr)
        return 1
    print(f"licence headers: clean ({len(files)} files scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
