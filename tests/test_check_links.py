# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the Markdown relative-link checker."""

from __future__ import annotations

import contextlib
import io
import subprocess
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

    def run_check(self, *targets: str | Path) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        args = [str(t) for t in targets] if targets else [str(self.root)]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["check_links.py", *args])
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

    def test_badge_wrapped_links_are_checked(self) -> None:
        self.write("LICENSES/CC-BY-4.0.txt", "CC BY 4.0\n")
        readme = self.write(
            "README.md",
            "[![Docs: CC BY 4.0](https://img.shields.io/badge/docs.svg)](LICENSES/CC-BY-4.0.txt)\n",
        )
        code, _out, err = self.run_check(readme)
        self.assertEqual(code, 0, msg=err)

        self.write(
            "README.md",
            "[![badge](https://img.shields.io/x.svg)](missing/license.txt)\n",
        )
        code, _out, err = self.run_check(readme)
        self.assertEqual(code, 1)
        self.assertIn("README.md:1: missing/license.txt", err)

    def test_wiki_extensionless_link_only_resolves_under_docs_wiki(self) -> None:
        self.write("docs/wiki/Phase-0-Plan.md", "# Phase 0\n")
        self.write("docs/wiki/Home.md", "[Plan](Phase-0-Plan)\n")
        self.write("other/wiki/Page.md", "# Page\n")
        other = self.write("other/wiki/Home.md", "[Page](Page)\n")

        code, _out, err = self.run_check(self.root / "docs/wiki/Home.md")
        self.assertEqual(code, 0, msg=err)

        code, _out, err = self.run_check(other)
        self.assertEqual(code, 1)
        self.assertIn("other/wiki/Home.md:1: Page", err)

    def test_root_relative_target_is_reported_as_broken(self) -> None:
        self.write("docs/target.md", "# Target\n")
        index = self.write("docs/index.md", "[root](/docs/target.md)\n")

        code, _out, err = self.run_check(index)
        self.assertEqual(code, 1)
        self.assertIn("docs/index.md:1: /docs/target.md", err)

    def test_multiple_explicit_paths_and_git_tracked_filtering(self) -> None:
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "agent@example.com"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=self.root, check=True, capture_output=True)

        good_a = self.write("a.MD", "[b](b.md)\n")
        good_b = self.write("b.md", "# B\n")
        subprocess.run(["git", "add", "a.MD", "b.md"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=self.root, check=True, capture_output=True)

        # Untracked local notes (e.g. .agents/ or scratch markdown) must be ignored for `.`.
        self.write(".agents/skill.md", "[broken](does_not_exist.md)\n")
        self.write("scratch.md", "[broken](does_not_exist.md)\n")

        with contextlib.chdir(self.root):
            code, out, err = self.run_check(".")
        self.assertEqual(code, 0, msg=err)
        self.assertIn("2 markdown files scanned", out)

        bad_c = self.write("c.md", "[missing](nope.md)\n")
        code, _out, err = self.run_check(good_a, good_b, bad_c)
        self.assertEqual(code, 1)
        self.assertIn("c.md:1: nope.md", err)


if __name__ == "__main__":
    unittest.main()
