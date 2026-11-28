# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the Markdown relative-link checker."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from tools.check_links import main


class TestCheckLinks(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, rel: str, content: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def run_check(self, target: Path | None = None) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        arg = str(target or self.root)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["check_links.py", arg])
        return code, out.getvalue(), err.getvalue()

    def test_valid_relative_links_and_ignored_targets_pass(self) -> None:
        self.write("docs/target.md", "# Target\n")
        self.write("docs/img.png", "png")
        self.write(
            "docs/index.md",
            "\n".join(
                [
                    "[good](target.md)",
                    "[with anchor](target.md#section)",
                    "[with query](target.md?plain=1)",
                    "![image](img.png)",
                    "[same-page](#heading)",
                    "[web](https://example.com/missing)",
                    "[mail](mailto:test@example.com)",
                ]
            )
            + "\n",
        )
        # Broken links inside skipped directories must not be reported.
        self.write(".venv/broken.md", "[bad](missing.md)\n")
        self.write(".bend-cache/broken.md", "[bad](missing.md)\n")
        self.write("node_modules/broken.md", "[bad](missing.md)\n")

        code, out, err = self.run_check()
        self.assertEqual(code, 0, msg=err)
        self.assertIn("clean", out)

    def test_broken_relative_link_fails_and_reports_location(self) -> None:
        self.write("docs/target.md", "# Target\n")
        self.write(
            "docs/index.md",
            "[ok](target.md)\n[broken](missing_note.md#part)\n",
        )

        code, _out, err = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("docs/index.md:2: missing_note.md#part", err)

    def test_wiki_extensionless_link_resolves_to_markdown(self) -> None:
        self.write("docs/wiki/Phase-0-Plan.md", "# Phase 0\n")
        self.write("docs/wiki/Home.md", "[Plan](Phase-0-Plan)\n")

        code, _out, err = self.run_check()
        self.assertEqual(code, 0, msg=err)


if __name__ == "__main__":
    unittest.main()
