#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reject CRLF, trailing whitespace and missing final newlines."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._files import resolve  # noqa: E402

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache"}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".pdf", ".age"}


def main(argv: list[str]) -> int:
    files = [p for p in resolve(argv[1:]) if not any(part in SKIP_DIRS for part in p.parts)]

    problems: list[str] = []
    for path in files:
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\r\n" in raw:
            problems.append(f"{path.as_posix()}: CRLF line endings")
            continue
        if b"\0" in raw:
            continue
        text = raw.decode("utf-8", errors="ignore")
        for number, line in enumerate(text.splitlines(), start=1):
            if line != line.rstrip():
                problems.append(f"{path.as_posix()}:{number}: trailing whitespace")
        if text and not text.endswith("\n"):
            problems.append(f"{path.as_posix()}: missing final newline")

    if problems:
        for item in problems[:50]:
            print(item, file=sys.stderr)
        if len(problems) > 50:
            print(f"... and {len(problems) - 50} more", file=sys.stderr)
        return 1
    print("whitespace: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
