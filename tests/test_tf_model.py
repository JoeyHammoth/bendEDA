# SPDX-License-Identifier: Apache-2.0
"""The model side of TF (step 2 of `docs/research/2026-11-28-tf-run-design.md`).

These tests compile the real judge module with the pinned compiler and execute it,
because the thing under test is precisely the boundary that cannot be guessed:
how a law's claim is rewritten into a function, and what the compiled module
returns for a state. A test with a stub evaluator would pass while the rewrite was
wrong.

They skip when no pinned compiler is configured, and the skip says what was not
measured. The job that owns this path is `bend and EDA gates`; the Python test
jobs have no compiler and have nothing to say about it.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from bendeda import tf
from bendeda.conformance.vector_path import find_bend_toolchain
from bendeda.laws.manifest import Manifest
from bendeda.laws.source import parse

ROOT = Path(__file__).resolve().parents[1]
B1 = ROOT / "tasks" / "seq" / "B1_fifo"


def compiler_missing() -> str | None:
    bun, cli = find_bend_toolchain()
    if not bun or not cli:
        return "no pinned Bend compiler (BENDEDA_BUN / BENDEDA_BEND_CLI), so no judge was run"
    if shutil.which("node") is None:
        return "no node on PATH, so the emitted judge module cannot be executed"
    return None


class TestJudgeGeneration(unittest.TestCase):
    """The rewrite, which needs no compiler."""

    def setUp(self) -> None:
        self.manifest = Manifest.load(B1 / "laws.manifest.yaml")
        self.laws = parse((B1 / "LAWS.bend").read_text(encoding="utf-8"), B1 / "LAWS.bend")
        self.model = (B1 / "model.bend").read_text(encoding="utf-8")

    def test_every_translated_law_gets_a_judge(self) -> None:
        judges, problems = tf.build_judges(self.model, self.manifest, self.laws)
        self.assertEqual(problems, [])
        self.assertEqual(len(judges), 19)
        self.assertEqual(len({judge.fn for judge in judges}), 19)

    def test_the_rewrite_binds_the_trace_not_the_law_binders(self) -> None:
        judges, _ = tf.build_judges(self.model, self.manifest, self.laws)
        by_law = {judge.law: judge for judge in judges}
        # Pop-from-full keeps the second element: the law's `b` becomes the pre-state's
        # second field, not a fresh binder the caller could supply.
        self.assertEqual(
            by_law["fifo_f07_pop_full_next_head"].expression,
            "U32.is_eq(dout(step(s0, Pop{})), tf_second(s1))",
        )
        self.assertEqual(by_law["fifo_f07_pop_full_next_head"].params, ("state", "state"))
        # Push carries the input, and the law uses it twice; affine bindings mean two
        # parameters that the driver fills with the same value.
        self.assertEqual(
            by_law["fifo_f02_push_empty_head"].expression,
            "U32.is_eq(dout(step(s0, Push{din0})), din1)",
        )
        self.assertEqual(
            by_law["fifo_f02_push_empty_head"].params, ("state", "din", "din")
        )
        # A Bool claim compared against another Bool needs an equality; Bool has no
        # `is_eq` in Base, so it is `not (xor l r)`.
        self.assertEqual(
            by_law["fifo_s02_full_iff_count_depth"].expression,
            "Bool.not(Bool.xor(is_full(s0), Nat.is_eq(count(s1), 2n)))",
        )

    def test_a_plan_that_contradicts_the_claim_is_a_problem_not_a_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "B1_fifo"
            shutil.copytree(B1, root)
            manifest_path = root / "laws.manifest.yaml"
            text = manifest_path.read_text(encoding="utf-8")
            # L011 accepts this shape; tf does not, because the stimulus it asks for
            # would never reach the law.
            broken = text.replace(
                "        ops: [Pop]\n        observe: [dout]\n        window: 1\n"
                "        distinct: [a, b]",
                "        ops: [Idle]\n        observe: [dout]\n        window: 1\n"
                "        distinct: [a, b]",
                1,
            )
            self.assertNotEqual(broken, text)
            manifest_path.write_text(broken, encoding="utf-8", newline="")
            report = tf.evaluate(root, traces=8, cycles=4)
            self.assertEqual(report.exit_code(), tf.EXIT_NOTHING_MEASURED)
            self.assertTrue(
                any("never exercise the law" in problem for problem in report.problems),
                report.problems,
            )


class TestEvaluation(unittest.TestCase):
    """The compiled evaluator on the reference model and on a broken one."""

    def setUp(self) -> None:
        reason = compiler_missing()
        if reason:
            self.skipTest(reason)

    def test_every_law_is_exercised_and_agrees_on_the_reference_model(self) -> None:
        report = tf.evaluate(B1, traces=300, cycles=8)
        self.assertEqual(report.problems, [])
        self.assertEqual(report.exit_code(), tf.EXIT_OK, report.as_json())
        self.assertEqual(len(report.rows), 19)
        unexercised = [row.id for row in report.rows if row.exercised == 0]
        self.assertEqual(unexercised, [])
        disagreed = {row.id: row.first_disagreement for row in report.rows if row.disagreed}
        self.assertEqual(disagreed, {})
        # A state invariant is evaluated at every cycle; an operation law only where
        # its plan's level and operation hold, so the two counts must differ.
        rows = {row.id: row for row in report.rows}
        self.assertEqual(rows["FIFO-S-01"].exercised, 300 * 8)
        self.assertLess(rows["FIFO-F-05"].exercised, rows["FIFO-S-01"].exercised)

    def test_a_broken_model_is_caught_by_the_law_it_breaks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "B1_fifo"
            shutil.copytree(B1, root)
            model_path = root / "model.bend"
            text = model_path.read_text(encoding="utf-8")
            # Pop from full must hand the second element to `dout`; the design's own
            # head instead is wrong at exactly FIFO-F-07 and nothing else.
            broken = text.replace(
                "            case Pop{}:\n              MkFifo{b, b, Half{}}",
                "            case Pop{}:\n              MkFifo{a, b, Half{}}",
            )
            self.assertNotEqual(broken, text)
            model_path.write_text(broken, encoding="utf-8", newline="")
            report = tf.evaluate(root, traces=300, cycles=8)
            self.assertEqual(report.problems, [])
            rows = {row.id: row for row in report.rows}
            self.assertGreater(rows["FIFO-F-07"].disagreed, 0)
            # The disagreement is replayable: it names the trace, the cycle and the
            # pre-state's elements, so the same two verdicts can be recomputed.
            first = rows["FIFO-F-07"].first_disagreement
            self.assertIsNotNone(first["binders"]["head"])
            self.assertIsNotNone(first["binders"]["second"])
            self.assertEqual(report.exit_code(), tf.EXIT_DISAGREEMENT)
            # The other pop laws constrain count and level, which this mutant leaves
            # alone; a law that fires here would be a judge that cannot tell what it
            # is measuring.
            self.assertEqual(rows["FIFO-F-06"].disagreed, 0)

    def test_a_law_without_a_plan_is_reported_rather_than_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "B1_fifo"
            shutil.copytree(B1, root)
            manifest_path = root / "laws.manifest.yaml"
            text = manifest_path.read_text(encoding="utf-8")
            # Remove one translated law's whole plan block, keeping the law translated.
            block = (
                "      sva: p_pop_empty_noop\n"
                "      template: implication_v1\n"
                "      fidelity_plan:\n"
                "        level: Empty\n"
                "        ops: [Pop]\n"
                "        observe: [count]\n"
                "        window: 1\n"
            )
            self.assertIn(block, text)
            manifest_path.write_text(
                text.replace(block, "      sva: p_pop_empty_noop\n"), encoding="utf-8", newline=""
            )
            report = tf.evaluate(root, traces=4, cycles=2)
            self.assertTrue(
                any("fifo_f05_pop_empty_noop: the translation declares no fidelity_plan" in problem
                    for problem in report.problems),
                report.problems,
            )
            self.assertEqual(report.exit_code(), tf.EXIT_NOTHING_MEASURED)


if __name__ == "__main__":
    unittest.main()
