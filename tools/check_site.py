#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cheap structural checks on the documentation site: the entry point exists,
local assets and links resolve, and no page is left with an unresolved template
marker."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REF = re.compile(r'(?:href|src)="([^"]+)"')


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else "site")
    index = root / "index.html"
    if not index.exists():
        print(f"site: missing {index}", file=sys.stderr)
        return 1

    problems: list[str] = []
    pages = list(root.glob("*.html"))
    for page in pages:
        text = page.read_text(encoding="utf-8", errors="ignore")
        for marker in ("{{", "TODO(", "lorem ipsum"):
            if marker in text:
                problems.append(f"{page.name}: unresolved marker {marker!r}")
        for ref in REF.findall(text):
            if ref.startswith(("http://", "https://", "mailto:", "#", "data:")):
                continue
            target = (page.parent / ref.split("#", 1)[0]).resolve()
            if not target.exists():
                problems.append(f"{page.name}: broken reference {ref}")

    if problems:
        for item in problems:
            print(f"site: {item}", file=sys.stderr)
        return 1
    print(f"site: clean ({len(pages)} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
