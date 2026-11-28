#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that relative inline Markdown links and images resolve on disk."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._files import resolve  # noqa: E402

SKIP_DIRS = {".git", ".venv", "venv", ".bend-cache", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache"}
LINK_TARGET = re.compile(r"\]\(([^)\r\n]+)\)")
SKIP_PREFIXES = ("http://", "https://", "mailto:")


def extract_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")].strip()
    # Strip optional Markdown link title after whitespace, e.g. path.md "title".
    parts = target.split(None, 1)
    return parts[0] if parts else ""


def is_docs_wiki_page(path: Path) -> bool:
    resolved = path.resolve()
    return resolved.parent.name == "wiki" and resolved.parent.parent.name == "docs"


def check_file(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    findings: list[tuple[int, str]] = []
    in_fence = False
    wiki_page = is_docs_wiki_page(path)
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        # Ignore inline code spans so example syntax like `[text](target)` is not checked.
        cleaned = re.sub(r"`[^`]*`", "", line)
        for match in LINK_TARGET.finditer(cleaned):
            target = extract_target(match.group(1))
            if not target or target.startswith("#") or target.startswith(SKIP_PREFIXES):
                continue
            rel = target.split("#", 1)[0].split("?", 1)[0]
            if not rel:
                continue
            if rel.startswith("/"):
                findings.append((line_no, target))
                continue
            resolved = (path.parent / rel).resolve()
            if resolved.exists():
                continue
            # GitHub Wiki pages under docs/wiki/ link to sibling pages without ".md".
            if wiki_page and not resolved.suffix and resolved.with_suffix(".md").exists():
                continue
            findings.append((line_no, target))
    return findings


def main(argv: list[str]) -> int:
    files = sorted(
        {
            p
            for p in resolve(argv[1:])
            if p.suffix.lower() == ".md" and not any(part in SKIP_DIRS for part in p.parts)
        }
    )

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
