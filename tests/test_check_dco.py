# SPDX-License-Identifier: Apache-2.0
"""The DCO check must read every commit in a multi-commit pull request.

A one-commit pull request passed with the old parser, which split the whole
`git log` stream on NUL even though git separates records with a newline. This
test builds a repository with several commits so the second record is exercised.
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.check_dco import commits, main


class TestDco(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.git("init", "-b", "main")
        self.git("config", "user.email", "agent@example.com")
        self.git("config", "user.name", "Test Agent")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True, check=True
        ).stdout.strip()

    def commit(self, message: str, sign: bool = True) -> str:
        (self.root / "work.txt").write_text(message, encoding="utf-8")
        self.git("add", "-A")
        argv = ["commit", "-m", message]
        if sign:
            argv.append("-s")
        self.git(*argv)
        return self.git("rev-parse", "HEAD")

    def check(self, base: str) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.chdir(self.root), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = main(["check_dco.py", base])
        return code, err.getvalue()

    def test_every_commit_is_read_not_just_the_first(self) -> None:
        base = self.commit("base")
        self.commit("first feature commit")
        self.commit("second feature commit")
        self.assertEqual(len(commits(base, cwd=self.root)), 2)
        code, err = self.check(base)
        self.assertEqual(code, 0, msg=err)

    def test_an_unsigned_later_commit_is_named(self) -> None:
        base = self.commit("base")
        self.commit("signed feature commit")
        self.commit("unsigned feature commit", sign=False)
        code, err = self.check(base)
        self.assertEqual(code, 1)
        self.assertIn("unsigned feature commit", err)

    def test_an_unsigned_first_commit_is_still_caught(self) -> None:
        base = self.commit("base")
        self.commit("unsigned first commit", sign=False)
        self.commit("signed second commit")
        code, err = self.check(base)
        self.assertEqual(code, 1)
        self.assertIn("unsigned first commit", err)


if __name__ == "__main__":
    unittest.main()
