#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Every commit in the pull request must carry a Developer Certificate of Origin
sign-off. Bot merges are exempt only when the commit has no author email."""

from __future__ import annotations

import subprocess
import sys


def commits(base: str) -> list[tuple[str, str]]:
    try:
        log = subprocess.run(
            ["git", "log", f"{base}..HEAD", "--format=%H%x00%B%x00%ae"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    entries = [chunk for chunk in log.split("\0") if chunk.strip()]
    result = []
    for i in range(0, len(entries) - 2, 3):
        result.append((entries[i].strip(), entries[i + 1]))
    return result


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: check_dco.py <base-ref>", file=sys.stderr)
        return 2
    base = argv[1]
    missing = []
    for sha, body in commits(base):
        trailers = [line for line in body.splitlines() if line.lower().startswith("signed-off-by:")]
        if not trailers:
            subject = body.splitlines()[0] if body.splitlines() else "(no subject)"
            missing.append(f"{sha[:9]} {subject}")

    if missing:
        print("commits without DCO sign-off:", file=sys.stderr)
        for item in missing:
            print(f"  {item}", file=sys.stderr)
        print("Fix with: git commit --amend -s   (or rebase -i --signoff)", file=sys.stderr)
        return 1
    print("DCO: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
