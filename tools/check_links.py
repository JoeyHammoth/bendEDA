#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that relative inline Markdown links and images resolve on disk."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", ".venv", ".bend-cache", "node_modules", "__pycache__"}
INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\r\n]+)\)")
SKIP_PREFIXES = ("http://", "https://", "mailto:")


def iter_markdown_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() == ".md" else []
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith(".md"):
                files.append(Path(dirpath) / name)
    return files


def extract_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")].strip()
    # Strip optional Markdown link title after whitespace, e.g. path.md "title".
    parts = target.split(None, 1)
    return parts[0] if parts else ""


def check_file(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    findings: list[tuple[int, str]] = []
    in_fence = False
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        # Ignore inline code spans so example syntax like `[text](target)` is not checked.
        cleaned = re.sub(r"`[^`]*`", "", line)
        for match in INLINE_LINK.finditer(cleaned):
            target = extract_target(match.group(1))
            if not target or target.startswith("#") or target.startswith(SKIP_PREFIXES):
                continue
            rel = target.split("#", 1)[0].split("?", 1)[0]
            if not rel:
                continue
            resolved = (path.parent / rel).resolve()
            if resolved.exists():
                continue
            # GitHub Wiki pages under docs/wiki/ link to sibling pages without ".md".
            if "wiki" in path.parts and not resolved.suffix and resolved.with_suffix(".md").exists():
                continue
            findings.append((line_no, target))
    return findings


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".")
    files = iter_markdown_files(root)

    problems: list[str] = []
    for md_file in files:
        for line_no, target in check_file(md_file):
            problems.append(f"{md_file.as_posix()}:{line_no}: {target}")

    if problems:
        for item in problems:
            print(item, file=sys.stderr)
        return 1
    print(f"links: clean ({len(files)} markdown files scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
