# SPDX-License-Identifier: Apache-2.0
"""The checker canary suite (issue #9).

Two kinds of test here. The unit tests pin the verdict classification and the
scoring rules, including the case that matters: a checker which accepts
everything must fail this suite. The live test runs all controls through the
pinned compiler and is skipped where no compiler exists — but a *skipped* run is
not evidence, which is why CI wires the same command into two jobs.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

from bendeda.canary import (
    CONTROLS,
    Checker,
    Outcome,
    SuiteResult,
    build_checker,
    negatives,
    positives,
    run_suite,
    select,
    stage_of,
)
from bendeda.canary.controls import ANY, ACCEPT, REFUSE
from bendeda.cli import EXIT_OK, main

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".bend-cache" / "canary" / "test"

ACCEPTED = "ALL PROOFS CHECK\nUse --verdict for mathematical validity.\n"

REFUSED_LAW = (
    "SOME PROOFS FAIL\nError:\n- expected : 300\n- observed : 44\nLocation: canary.sum_before_wrap\n"
    "6 | def canary.sum_before_wrap():\n7>|   {==}\n  |   ^^^^\n"
    "Note: the left side of the equality is the expected, the right side is the observed.\n"
)
REFUSED_UNDEFINED = (
    "SOME PROOFS FAIL\nError:\n- expected : a defined name\n- observed : Word.and_absorb\n"
)
REFUSED_TYPE = "SOME PROOFS FAIL\nError:\n- expected : Nat\n- observed : Bool\nContext:\n- a : Bool\n"
REFUSED_TERMINATION = (
    "SOME PROOFS FAIL\nError:\n- expected : a call smaller than c.law (arguments are read "
    "left to right: each passed unchanged until one shrinks)\n- observed : c.law\n"
)
REFUSED_TODO = "SOME PROOFS FAIL\nError: 1 TODO found.\nThe code is incomplete, and not a valid proof yet.\n"
KERNEL_MISSING = (
    'Error: BendTT infrastructure: the kernel did not build (lean: Executable not found in '
    '$PATH: "lean"); --verdict needs Lean v4.34.0\n'
)


def outcome(cid: str, expected: str, actual: str, stage: str | None, expected_stage: str = "law") -> Outcome:
    return Outcome(cid, "test", "fabricated", expected, expected_stage, actual, stage, "evidence", "cmd")


class TestCatalog(unittest.TestCase):
    def test_at_least_thirty_negative_controls(self) -> None:
        self.assertGreaterEqual(len(negatives()), 30)

    def test_ids_are_unique(self) -> None:
        ids = [c.id for c in CONTROLS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_the_families_the_issue_names_are_present(self) -> None:
        families = {c.family for c in negatives()}
        for required in ("arithmetic", "universal", "incomplete", "missing", "type", "termination", "axiom"):
            self.assertIn(required, families)

    def test_every_control_is_a_whole_bend_file(self) -> None:
        for control in CONTROLS:
            self.assertTrue(control.source.startswith("import Base"), control.id)
            self.assertIn("law ", control.source, control.id)
            self.assertNotIn("\t", control.source, control.id)

    def test_positives_exist_so_blanket_refusal_is_caught(self) -> None:
        self.assertGreaterEqual(len(positives()), 3)

    def test_declared_stages_are_known(self) -> None:
        known = {"law", "undefined", "order", "type", "termination", "todo", "front-end", ANY}
        for control in CONTROLS:
            self.assertIn(control.stage, known, control.id)

    def test_select_filters(self) -> None:
        self.assertEqual([c.id for c in select(only=["a01"])], ["a01"])
        self.assertTrue(all(c.family == "type" for c in select(families=["type"])))


class TestClassification(unittest.TestCase):
    def test_accepts(self) -> None:
        self.assertIn("ALL PROOFS CHECK", ACCEPTED)

    def test_stage_of_refusals(self) -> None:
        self.assertEqual(stage_of(REFUSED_LAW), "law")
        self.assertEqual(stage_of(REFUSED_UNDEFINED), "undefined")
        self.assertEqual(stage_of(REFUSED_TYPE), "type")
        self.assertEqual(stage_of(REFUSED_TERMINATION), "termination")
        self.assertEqual(stage_of(REFUSED_TODO), "todo")

    def test_unknown_refusal_is_front_end_not_law(self) -> None:
        self.assertEqual(stage_of("SOME PROOFS FAIL\nError: something unexpected\n"), "front-end")


class TestScoring(unittest.TestCase):
    def suite(self, *outcomes: Outcome) -> SuiteResult:
        result = SuiteResult("test", "default")
        result.outcomes.extend(outcomes)
        return result

    def test_clean_run_exits_zero(self) -> None:
        result = self.suite(
            outcome("a01", REFUSE, "refuse", "law"),
            outcome("p01", ACCEPT, "accept", None, ANY),
        )
        self.assertEqual(result.exit_code(), 0)
        self.assertEqual(result.report().false_accepts, 0)

    def test_a_false_accept_exits_one(self) -> None:
        result = self.suite(outcome("a01", REFUSE, "accept", None))
        self.assertEqual(result.exit_code(), 1)
        self.assertEqual(result.report().false_accepts, 1)

    def test_a_false_reject_exits_one(self) -> None:
        result = self.suite(outcome("p01", ACCEPT, "refuse", "law", ANY))
        self.assertEqual(result.exit_code(), 1)
        self.assertEqual(result.report().false_rejects, 1)

    def test_refusal_at_the_wrong_stage_exits_one(self) -> None:
        # Refused by a typo is refused, but it is not evidence about the checker.
        result = self.suite(outcome("a01", REFUSE, "refuse", "front-end"))
        self.assertEqual(result.exit_code(), 1)
        self.assertEqual(len(result.misplaced), 1)

    def test_any_stage_accepts_any_refusal(self) -> None:
        result = self.suite(outcome("s01", REFUSE, "refuse", "front-end", ANY))
        self.assertEqual(result.exit_code(), 0)

    def test_nothing_ran_exits_three(self) -> None:
        result = self.suite(outcome("a01", REFUSE, "unavailable", None))
        self.assertEqual(result.exit_code(), 3)

    def test_empty_suite_exits_three(self) -> None:
        self.assertEqual(SuiteResult("test", "default").exit_code(), 3)

    def test_a_crash_is_not_a_pass(self) -> None:
        result = self.suite(outcome("a01", REFUSE, "error", None))
        self.assertEqual(result.exit_code(), 1)


class TestTheSuiteCanFail(unittest.TestCase):
    """Meta-controls: the gate must fail when the checker misbehaves.

    This is the same discipline as the unmasked-add control for BendBV. A suite
    that cannot report a failure is worse than no suite, because it looks like
    one.
    """

    def run_with(self, script: str, controls: tuple) -> SuiteResult:
        checker = Checker([sys.executable, "-c", script], ROOT, "fake checker")
        return run_suite(controls, checker, WORK)

    def test_a_checker_that_accepts_everything_fails(self) -> None:
        result = self.run_with("print('ALL PROOFS CHECK')", select(only=["a01"]))
        self.assertEqual(result.exit_code(), 1)
        self.assertEqual(len(result.false_accepts), 1)

    def test_a_checker_that_refuses_everything_fails(self) -> None:
        script = "print('SOME PROOFS FAIL'); print('Error: 1 TODO found.')"
        result = self.run_with(script, select(only=["p01"]))
        self.assertEqual(result.exit_code(), 1)
        self.assertEqual(len(result.false_rejects), 1)

    def test_a_checker_that_cannot_run_exits_three(self) -> None:
        result = self.run_with("print('Error: BendTT infrastructure: the kernel did not build')",
                               select(only=["a01"]))
        self.assertEqual(result.exit_code(), 3)
        self.assertEqual(len(result.unavailable), 1)


class TestCliSurface(unittest.TestCase):
    def test_an_unrunnable_checker_is_exit_three_not_success(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["canary", "--local", "--bun", "definitely-not-here"])
        self.assertEqual(code, 3)
        self.assertIn("cannot run the checker", err.getvalue())
        self.assertIn("not a pass", err.getvalue())

    def test_no_matching_control_is_a_usage_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            code = main(["canary", "--local", "--only", "nope"])
        # The bun check comes first, so this is about the usage path only when it
        # gets past it; either way it must not be a success.
        self.assertNotEqual(code, EXIT_OK)


class TestLiveSuite(unittest.TestCase):
    """The real run. Skipped where no pinned compiler exists — never faked."""

    def setUp(self) -> None:
        self.checker = build_checker(local=True, root=ROOT)
        if isinstance(self.checker, str):
            self.skipTest(f"no pinned checker: {self.checker}")

    def test_every_control_lands_where_it_is_expected(self) -> None:
        result = run_suite(CONTROLS, self.checker, WORK)
        problems = [o for o in result.outcomes if o.unhappy]
        detail = "\n".join(
            f"  {o.id} {o.family}: expected {o.expected} at {o.expected_stage}, "
            f"got {o.actual} at {o.stage} | {o.evidence}"
            for o in problems
        )
        self.assertEqual(result.exit_code(), 0, msg=detail)
        self.assertGreaterEqual(result.negatives_run, 30)
        self.assertGreaterEqual(result.law_stage, 8, "too few controls reach the law layer")


if __name__ == "__main__":
    unittest.main()
