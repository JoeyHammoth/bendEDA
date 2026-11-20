"""BendBV gate (issue #8).

Two things are checked, and the second is the point: the library's claims must
check, and a file with mask(w) deleted must be refused. A gate that accepted
only the first would be indifferent to the bug the mask exists to prevent.

Both run through the pinned compiler: locally via BENDEDA_BUN and
BENDEDA_BEND_CLI, in CI through the same two variables.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "bv" / "bv.bend"
CONTROL = ROOT / "bv" / "negative" / "unmasked_add.bend"
NL = chr(10)


def bend_command() -> list[str] | None:
    bun = os.environ.get("BENDEDA_BUN")
    cli = os.environ.get("BENDEDA_BEND_CLI")
    if bun and cli and Path(cli).exists():
        return [bun, cli]
    found = shutil.which("bend")
    return [found] if found else None


def code_only(path: Path) -> str:
    """The file with comment lines removed."""
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    return NL.join(lines)


class TestBendBvSource(unittest.TestCase):
    def test_every_operation_is_masked(self):
        source = NL.join(LIBRARY.read_text(encoding="utf-8").splitlines())
        self.assertIn(
            "def bv_add(w: Nat, a: U32, b: U32) -> U32:" + NL + "  mask(w, U32.add(a, b))",
            source,
        )
        self.assertIn(
            "def bv_sub(w: Nat, a: U32, b: U32) -> U32:" + NL + "  mask(w, U32.sub(a, b))",
            source,
        )

    def test_the_control_deletes_the_mask(self):
        # Comments mention the mask on purpose; the code must not use it.
        code = code_only(CONTROL)
        self.assertNotIn("mask(", code)
        self.assertIn("U32.add(a, b)", code)
        self.assertIn("bv_add_unmasked.wrap8", code)

    def test_the_control_claims_what_the_library_proves(self):
        # Same width, same inputs, same expected value: only the mask differs,
        # so a failure on one side cannot be a difference in what was claimed.
        self.assertIn("bv_add(8n, 200, 100) == 44", code_only(LIBRARY))
        self.assertIn("bv_add_unmasked(200, 100) == 44", code_only(CONTROL))


class TestBendBvProofs(unittest.TestCase):
    def setUp(self):
        self.command = bend_command()
        if self.command is None:
            self.skipTest(
                "no Bend compiler: set BENDEDA_BUN and BENDEDA_BEND_CLI, or put bend on PATH"
            )

    def gate(self, path: Path) -> str:
        argv = self.command + [str(path)]
        try:
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
        except OSError:
            # On Windows the bun that npm installs is a POSIX shell shim, not a
            # PE image, so it needs a shell to start. CI runs Linux and never
            # takes this path.
            shell = " ".join(shlex.quote(part) for part in argv)
            result = subprocess.run(
                ["bash", "-c", shell], cwd=ROOT, capture_output=True, text=True
            )
        return result.stdout + result.stderr

    def test_the_library_checks(self):
        output = self.gate(LIBRARY)
        self.assertIn("ALL PROOFS CHECK", output, output)

    def test_the_unmasked_control_is_refused(self):
        output = self.gate(CONTROL)
        self.assertIn("SOME PROOFS FAIL", output, output)
        self.assertNotIn("ALL PROOFS CHECK", output, output)
        # The refusal must be the arithmetic, not a file that failed to parse.
        self.assertIn("300", output, output)
        self.assertIn("44", output, output)
