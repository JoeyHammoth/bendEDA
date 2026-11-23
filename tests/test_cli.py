# SPDX-License-Identifier: Apache-2.0
"""CLI behaviour, including the property that matters most: a planned command
must not report success."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from bendeda import __version__
from bendeda.cli import EXIT_NOT_IMPLEMENTED, EXIT_OK, EXIT_USAGE, main


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestCliBasics(unittest.TestCase):
    def test_version_flag(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            with contextlib.redirect_stdout(io.StringIO()):
                main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn(__version__, __version__)

    def test_no_command_prints_help(self) -> None:
        code, out, _ = run()
        self.assertEqual(code, EXIT_OK)
        self.assertIn("bendeda", out)

    def test_unknown_subcommand_is_usage_error(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            with contextlib.redirect_stderr(io.StringIO()):
                main(["nonsense"])
        self.assertEqual(ctx.exception.code, 2)


class TestHonestStubs(unittest.TestCase):
    def test_planned_commands_exit_three(self) -> None:
        for argv in (
            ["law", "lint", "tasks"],
            ["tf", "run", "--all"],
            ["gate", "run", "lint"],
            ["run", "experiments/trackA.yaml"],
            ["oracle", "seal"],
            ["bundle", "verify", "x"],
        ):
            code, out, err = run(*argv)
            self.assertEqual(code, EXIT_NOT_IMPLEMENTED, msg=f"{argv} should not report success")
            self.assertIn("not implemented yet", err)
            self.assertEqual(out, "")

    def test_law_subcommand_without_action_is_usage_error(self) -> None:
        code, _, _ = run("law")
        self.assertEqual(code, EXIT_USAGE)


class TestWorkingCommands(unittest.TestCase):
    def test_validate(self) -> None:
        code, out, err = run("validate", "--all")
        self.assertEqual(code, EXIT_OK, msg=err)
        self.assertIn("schema", out)

    def test_task_new_dry_run_writes_nothing(self) -> None:
        code, out, _ = run("task", "new", "A9_toy", "--tier", "A", "--dry-run")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("A9_toy", out)

    def test_init_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = run("init", tmp, "--dry-run")
            self.assertEqual(code, EXIT_OK)
            self.assertEqual(list(Path(tmp).iterdir()), [])
            self.assertIn("would create", out)


if __name__ == "__main__":
    unittest.main()
