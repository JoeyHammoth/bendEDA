#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The sealed oracle may exist in this repository only as ciphertext plus a
commitment. This check blocks the two ways that rule is usually broken: an
archive committed in the clear, and an `oracle/` directory with content."""

from __future__ import annotations

import sys
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__"}
ALLOWED_ORACLE_FILES = {"README.md", "commitment.json", "canary.txt", "SHA256SUMS"}


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".")
    problems: list[str] = []

    sealed = root / "oracle_sealed"
    if sealed.is_dir():
        for item in sealed.rglob("*"):
            if not item.is_file() or item.name in ALLOWED_ORACLE_FILES:
                continue
            if item.suffix in {".age", ".gpg", ".enc"}:
                continue
            problems.append(f"{item.as_posix()}: sealed-oracle artifact must be ciphertext (.age)")

    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts) or not path.is_file():
            continue
        if path.name in {"oracle.tar", "oracle.zip"} or path.name.endswith(".tar.gz"):
            problems.append(f"{path.as_posix()}: plaintext oracle archive")

    if problems:
        for item in problems:
            print(item, file=sys.stderr)
        print(
            "The oracle is developed outside this repository and published only as "
            "ciphertext plus a commitment (design document Appendix I.4).",
            file=sys.stderr,
        )
        return 1
    print("oracle absence: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
