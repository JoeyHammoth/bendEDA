# SPDX-License-Identifier: Apache-2.0
"""Model mutation (issue #10, gate LA3).

The checker is faked, and that is the point of these tests: they assert that the
tool attributes a kill to the right law and refuses to call an under-mutated
model adequate, independently of whether Bend happens to be installed.
`TestLiveMutation` runs the same path through the pinned compiler when it is
available.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from bendeda.canary.runner import Checker
from bendeda.laws.mutate import (
    EXIT_FAIL,
    EXIT_NOTHING_MEASURED,
    EXIT_OK,
    candidates,
    isolate_laws,
    run_mutation,
    strip_imports,
)
from bendeda.laws.source import parse

NL = chr(10)

MODEL = NL.join(
    [
        "import Base",
        "",
        "def toy_step(x: U32) -> U32:",
        "  U32.add(x, 1)",
        "",
    ]
)

LAWS = NL.join(
    [
        "import Base",
        "",
        "law toy_s01_step:",
        "  for x: U32",
        "  {toy_step(x) == U32.add(x, 1) : U32}",
        "",
        "def toy_s01_step(x):",
        "  {==}",
        "",
    ]
)

CHECKER = Checker(["true"], Path("."), "fake")


def fake_checker(argv, cwd, timeout):  # type: ignore[no-untyped-def]
    """The law holds only while the model has not swapped add for sub."""
    path = Path(cwd) / Path(argv[-1])
    text = path.read_text(encoding="utf-8")
    if "U32.sub(x, 1)" in text:
        return 1, "SOME PROOFS FAIL" + NL + "Error:" + NL + "- expected : 2" + NL + "- observed : 0"
    return 0, "ALL PROOFS CHECK"


class TestCatalogue(unittest.TestCase):
    def test_one_mutant_per_site(self) -> None:
        mutants = candidates(MODEL)
        self.assertEqual(len(mutants), 2)
        self.assertIn("U32.add -> U32.sub", mutants[0].description)
        self.assertEqual(mutants[0].line, 4)
        self.assertIn("U32.sub", mutants[0].text)
        self.assertIn("U32.add(x, 2)", mutants[1].text)

    def test_comments_are_not_mutated(self) -> None:
        mutants = candidates("# U32.add(1, 2) here" + NL + "def toy_id(x: U32) -> U32:" + NL + "  x" + NL)
        self.assertEqual(mutants, [])

    def test_the_model_cannot_be_imported_so_it_is_inlined(self) -> None:
        inlined = strip_imports(MODEL)
        self.assertNotIn("import", inlined)
        self.assertTrue(inlined.startswith("def toy_step"))


class TestIsolation(unittest.TestCase):
    def test_dependencies_precede_the_law_that_uses_them(self) -> None:
        parsed = parse(
            "import Base" + NL
            + "law toy_helper:" + NL
            + "  for x: U32" + NL
            + "  {U32.add(x, 0) == x : U32}" + NL
            + "def toy_helper(x):" + NL
            + "  {==}" + NL
            + "law toy_s01_uses_helper:" + NL
            + "  for x: U32" + NL
            + "  {toy_helper_value(x) == U32.add(x, 0) : U32}" + NL
            + "def toy_s01_uses_helper(x):" + NL
            + "  toy_helper(x)" + NL
        )
        isolated = isolate_laws(parsed, strip_imports(MODEL))
        text = next(item.text for item in isolated if item.name == "toy_s01_uses_helper")
        self.assertIn("law toy_helper", text)
        self.assertIn("def toy_helper", text)
        self.assertLess(text.index("law toy_helper"), text.index("law toy_s01_uses_helper"))

    def test_unrelated_laws_are_not_included(self) -> None:
        parsed = parse(
            "law toy_s01_a:" + NL
            + "  for x: U32" + NL
            + "  {U32.add(x, 0) == x : U32}" + NL
            + "def toy_s01_a(x):" + NL
            + "  {==}" + NL
            + "law toy_s02_b:" + NL
            + "  for x: U32" + NL
            + "  {U32.sub(x, x) == 0 : U32}" + NL
            + "def toy_s02_b(x):" + NL
            + "  {==}" + NL
        )
        isolated = isolate_laws(parsed, strip_imports(MODEL))
        text = next(item.text for item in isolated if item.name == "toy_s01_a")
        self.assertNotIn("toy_s02_b", text)


class TestScoring(unittest.TestCase):
    def test_a_kill_is_attributed_to_the_law_that_noticed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_mutation(
                model_text=MODEL,
                laws_file=parse(LAWS),
                checker=CHECKER,
                workdir=Path(tmp),
                invoke=fake_checker,
            )
            self.assertEqual(len(report.mutants), 2)
            self.assertEqual(report.mutants[0].killed, ["toy_s01_step"])
            self.assertEqual(report.mutants[1].survived, ["toy_s01_step"])
            self.assertEqual(report.law_records()["toy_s01_step"], {"killed_by": 1, "total": 2})
            self.assertEqual(report.exit_code(min_mutants=2, min_kill=0.5), EXIT_OK)
            self.assertEqual(report.as_json(2, 0.5)["laws"]["toy_s01_step"]["killed_by"], 1)

    def test_an_under_mutated_model_is_not_adequate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_mutation(
                model_text=MODEL,
                laws_file=parse(LAWS),
                checker=CHECKER,
                workdir=Path(tmp),
                invoke=fake_checker,
            )
            self.assertEqual(report.exit_code(), EXIT_FAIL)
            self.assertFalse(report.as_json()["summary"]["ok"])

    def test_a_model_with_no_sites_measures_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_mutation(
                model_text="def toy_id(x: U32) -> U32:" + NL + "  x" + NL,
                laws_file=parse(LAWS),
                checker=CHECKER,
                workdir=Path(tmp),
                invoke=fake_checker,
            )
            self.assertEqual(report.mutants, [])
            self.assertEqual(report.exit_code(), EXIT_NOTHING_MEASURED)
            self.assertTrue(report.notes)

    def test_a_law_that_survives_every_mutant_fails_the_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_mutation(
                model_text=MODEL,
                laws_file=parse(LAWS),
                checker=CHECKER,
                workdir=Path(tmp),
                invoke=lambda argv, cwd, timeout: (0, "ALL PROOFS CHECK"),
            )
            self.assertEqual(report.survivors, ["toy_s01_step"])
            self.assertEqual(report.exit_code(min_mutants=1, min_kill=0.0), EXIT_FAIL)


@unittest.skipUnless(
    os.environ.get("BENDEDA_BUN") and os.environ.get("BENDEDA_BEND_CLI"),
    "no pinned compiler: set BENDEDA_BUN and BENDEDA_BEND_CLI",
)
class TestLiveMutation(unittest.TestCase):
    def test_the_kill_matrix_comes_from_the_real_checker(self) -> None:
        from bendeda.canary.runner import build_checker

        checker = build_checker(
            local=True,
            root=Path.cwd(),
            bun=os.environ["BENDEDA_BUN"],
            bend_cli=os.environ["BENDEDA_BEND_CLI"],
        )
        self.assertNotIsInstance(checker, str)
        with tempfile.TemporaryDirectory(dir=Path.cwd() / ".bend-cache") as tmp:
            report = run_mutation(
                model_text=MODEL,
                laws_file=parse(LAWS),
                checker=checker,  # type: ignore[arg-type]
                workdir=Path(tmp),
            )
            self.assertEqual(len(report.mutants), 2)
            # Both the operator swap and the bumped literal change what the law
            # claims, so the real checker kills both. The fake-checker test
            # above is what proves attribution when only one mutant is caught.
            self.assertEqual(report.mutants[0].killed, ["toy_s01_step"])
            self.assertEqual(report.mutants[1].killed, ["toy_s01_step"])
            self.assertEqual([m.errors for m in report.mutants], [[], []])


if __name__ == "__main__":
    unittest.main()
