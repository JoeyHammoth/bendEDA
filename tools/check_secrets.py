#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail if a credential-looking string is present in tracked text files.

Conservative on purpose: it looks for the shapes of real tokens, not the word
"token", so documentation about tokens does not trip it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools._files import resolve  # noqa: E402

PATTERNS = [
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "GitHub token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{40,}"), "GitHub fine-grained token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"sk-[A-Za-z0-9]{32,}"), "OpenAI-style API key"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"age1[0-9a-z]{50,}"), "age private key"),
]

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".pdf"}


def iter_files(targets: list[str]) -> list[Path]:
    paths = resolve(targets)
    return [
        p
        for p in paths
        if p.suffix.lower() not in SKIP_SUFFIXES
        and not any(part in SKIP_DIRS for part in p.parts)
    ]


def main(argv: list[str]) -> int:
    findings: list[str] = []
    for path in iter_files(argv[1:]):
        # The scanner itself contains the patterns it searches for.
        if path.name == "check_secrets.py":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:  # pragma: no cover - filesystem race
            print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
            continue
        for pattern, label in PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{path}:{line}: possible {label}")

    if findings:
        print("secret scan failed:", file=sys.stderr)
        for item in findings:
            print(f"  {item}", file=sys.stderr)
        print("Remove the value from history as well as the working tree.", file=sys.stderr)
        return 1
    print("secret scan: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
