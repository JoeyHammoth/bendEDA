# SPDX-License-Identifier: Apache-2.0
"""Shared file discovery.

Scanners must look at what the repository actually publishes, not at whatever
happens to sit in a working tree. Using `git ls-files` keeps local secrets,
virtualenvs and agent skills out of the results while still covering everything
that ships.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], capture_output=True, text=True, check=True
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [Path(p) for p in out.split("\0") if p]


def resolve(targets: list[str]) -> list[Path]:
    """Explicit paths are respected (pre-commit passes staged files); a bare
    '.' or an empty list means 'everything the repository tracks'."""
    if not targets or targets == ["."]:
        tracked = tracked_files()
        if tracked:
            return tracked
    paths: list[Path] = []
    for target in targets:
        path = Path(target)
        if path.is_file():
            paths.append(path)
        elif path.is_dir():
            paths.extend(p for p in path.rglob("*") if p.is_file())
    return paths
