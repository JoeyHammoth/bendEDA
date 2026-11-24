#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The sealed oracle may exist in this repository only as ciphertext plus a
commitment. This check blocks the three ways that rule is usually broken: an
archive committed in the clear, an `oracle/` directory with content, and the
canary GUID leaking into a task file."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# `.bend-cache` holds the pinned compiler archives downloaded by
# tools/fetch_bend.py. Those are local build inputs, not repository artifacts, and
# a fresh CI checkout never has them; flagging them here made the check fail on
# every developer machine for a reason that had nothing to do with the oracle.
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".bend-cache"}
ALLOWED_ORACLE_FILES = {"README.md", "commitment.json", "canary.txt", "SHA256SUMS"}
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def repository_files(root: Path) -> list[Path]:
    """Tracked files, because the contract is about what is committed.

    A staged build archive (`docker/archives/*.tar.gz`, gitignored) is a local build
    input like the compiler archives in `.bend-cache/`, and flagging it made the
    check fail for a reason unrelated to the oracle. A bare copy with no git falls
    back to walking the tree, so the check still bites where it can.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return [
            path
            for path in root.rglob("*")
            if path.is_file() and not any(part in SKIP_DIRS for part in path.parts)
        ]
    return [root / name for name in out.split("\0") if name]


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

    for path in repository_files(root):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
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

    canary = root / "oracle_sealed" / "canary.txt"
    if canary.exists():
        match = GUID.search(canary.read_text(encoding="utf-8"))
        if match is None:
            print(f"{canary.as_posix()}: no canary GUID", file=sys.stderr)
            return 1
        leaks = []
        tasks = root / "tasks"
        if tasks.exists():
            for path in tasks.rglob("*"):
                if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
                    continue
                if match.group(0) in path.read_text(encoding="utf-8", errors="ignore"):
                    leaks.append(path.as_posix())
        if leaks:
            for path in leaks:
                print(f"{path}: contains the sealed-oracle canary GUID", file=sys.stderr)
            print("The oracle has leaked into a task file; fix the source, not the check.", file=sys.stderr)
            return 1

    print("oracle absence: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
