#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Refuse changes to locked artifacts unless the PR is labelled `amendment`.

The manifest is `locked/LOCKED.json`, mapping repository-relative paths to the
SHA-256 they had when they were locked. Nothing is locked yet, so the guard is a
no-op until the first task is frozen -- but the mechanism exists before it is
needed, which is the point.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

MANIFEST = Path("locked/LOCKED.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def changed_files(base: str) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--base", default=None)
    parser.add_argument("--labels", default="")
    args = parser.parse_args()

    if not MANIFEST.exists():
        print("locked-file guard: no manifest, nothing is locked")
        return 0

    manifest: dict[str, str] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    labels = {label.strip() for label in args.labels.split(",") if label.strip()}

    changed = changed_files(args.base) if args.base else list(args.paths)
    violations = []
    for rel in changed:
        if rel not in manifest:
            continue
        path = Path(rel)
        if not path.exists():
            violations.append(f"{rel}: deleted")
            continue
        if sha256(path) != manifest[rel]:
            violations.append(f"{rel}: modified")

    if violations and "amendment" not in labels:
        print("locked-file guard: locked artifacts changed without the 'amendment' label", file=sys.stderr)
        for item in violations:
            print(f"  {item}", file=sys.stderr)
        print("Add an entry under amendments/ and label the pull request 'amendment'.", file=sys.stderr)
        return 1

    if violations:
        print("locked-file guard: changes permitted by the amendment label; update locked/LOCKED.json")
    else:
        print("locked-file guard: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
