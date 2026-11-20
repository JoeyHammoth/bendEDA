#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch the pinned Bend compiler sources and verify their digests.

Why fetch rather than vendor: THIRD_PARTY.md says third-party code is not
vendored, and a compiler that changes under a study is worse than one that is
absent. So the commit and the per-file digests are pinned, and this script
refuses to install a source tree that does not match.

Usage:
    python tools/fetch_bend.py                      # into .bend-cache/bend-2.0.40
    python tools/fetch_bend.py --into /tmp/bend-src
    python tools/fetch_bend.py --check-only         # verify an existing tree

Exit: 0 verified, 1 digest or download failure, 2 usage.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path

TAG = "v2.0.40"
COMMIT = "624dd9f4607cd29b0871a9b96d413bfb11e92f52"
RAW = f"https://raw.githubusercontent.com/bendlang/bend/{TAG}"
MANIFEST = Path("docker/bend-sources.sha256")
DEFAULT_INTO = Path(f".bend-cache/bend-{TAG.lstrip('v')}")


def read_manifest(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition("  ")
        if len(digest) != 64 or not name:
            raise ValueError(f"unparseable manifest line: {line!r}")
        entries.append((digest, name))
    return entries


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "bendeda-fetch-bend"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="fetch and verify pinned Bend sources")
    parser.add_argument("--into", default=str(DEFAULT_INTO))
    parser.add_argument("--check-only", action="store_true", help="verify an existing tree, download nothing")
    parser.add_argument("--tag", default=TAG)
    args = parser.parse_args(argv[1:])

    if not MANIFEST.exists():
        print(f"fetch_bend: manifest missing at {MANIFEST}", file=sys.stderr)
        return 2

    try:
        entries = read_manifest(MANIFEST)
    except ValueError as exc:
        print(f"fetch_bend: {exc}", file=sys.stderr)
        return 2

    root = Path(args.into)
    failures: list[str] = []
    for digest, name in entries:
        target = root / name
        if args.check_only:
            if not target.exists():
                failures.append(f"{name}: missing")
                continue
            actual = sha256(target)
            if actual != digest:
                failures.append(f"{name}: digest {actual} != pinned {digest}")
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and sha256(target) == digest:
            print(f"fetch_bend: {name} already pinned")
            continue
        url = f"{RAW}/{name}"
        try:
            payload = fetch(url)
        except (urllib.error.URLError, TimeoutError) as exc:
            failures.append(f"{name}: download failed ({exc})")
            continue
        actual = hashlib.sha256(payload).hexdigest()
        if actual != digest:
            failures.append(f"{name}: downloaded digest {actual} != pinned {digest}")
            continue
        target.write_bytes(payload)
        print(f"fetch_bend: {name} verified and written")

    if failures:
        print("fetch_bend: FAILED", file=sys.stderr)
        for item in failures:
            print(f"  {item}", file=sys.stderr)
        print("A mismatch is an incident: the pinned compiler is part of the protocol.", file=sys.stderr)
        return 1

    print(f"fetch_bend: {len(entries)} source file(s) verified at {args.tag} ({COMMIT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
