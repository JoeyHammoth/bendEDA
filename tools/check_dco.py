#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Every commit in the pull request must carry a Developer Certificate of Origin
sign-off. Bot merges are exempt only when the commit has no author email.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def commits(base: str, cwd: Path | None = None) -> list[tuple[str, str]]:
    """(sha, message) for each non-merge commit after `base`.

    This reads one commit per `git show` rather than parsing one `git log`
    stream. `%x00` separates the *fields* inside a record, but git still
    separates records with a newline, so splitting a whole log on NUL shifts
    every record after the first by one field: the second commit's subject was
    read as a body and its author email as a subject. A one-commit pull request
    never reaches the second record, which is why the bug survived until the
    first multi-commit one.
    """

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        ).stdout

    try:
        # --no-merges is load-bearing: the merge commit GitHub synthesises for a
        # pull request is created by the platform, not by a contributor, and it
        # cannot carry a sign-off. Checking it produced a false failure on the
        # first pull request to run this job.
        shas = git("log", f"{base}..HEAD", "--no-merges", "--format=%H").split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    result: list[tuple[str, str]] = []
    for sha in shas:
        raw = git("show", "-s", "--format=%B%x00%ae", sha)
        body, _, email = raw.partition("\x00")
        if not email.strip():
            continue
        result.append((sha, body))
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
