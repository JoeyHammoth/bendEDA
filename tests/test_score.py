# SPDX-License-Identifier: Apache-2.0
"""S, V and O, and the difference between "scored zero" and "not scored" (issue #15)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bendeda.budget import Limits
from bendeda.proxy import Policy
from bendeda.score import CRASH_EVENT, SUBMIT_EVENT, load, report, score

LIMITS = Limits(calls=10)


def events(*tools: str) -> list[dict]:
    return [{"seq": i, "tool": tool, "resource": "seq/B1_fifo/spec.md"} for i, tool in enumerate(tools, 1)]


class TestVerdicts(unittest.TestCase):
    def test_a_submission_before_exhaustion_gives_s_1(self) -> None:
        result = score(events("fs-read", SUBMIT_EVENT), LIMITS, {"lint": True}, {"sva": True})
        self.assertEqual((result.S, result.V, result.O), (1, 1, 1))
        self.assertTrue(result.complete)

    def test_exhaustion_is_a_scored_zero_not_an_exclusion(self) -> None:
        result = score(events(*["fs-read"] * 11), Limits(calls=10), {"lint": True}, {"sva": True})
        self.assertTrue(result.scored)
        self.assertEqual((result.S, result.V, result.O), (0, 0, 0))
        self.assertIn("exhausted", result.reason)

    def test_an_infrastructure_failure_is_not_scored_at_all(self) -> None:
        result = score(events("fs-read", "infra"), LIMITS)
        self.assertFalse(result.scored)
        self.assertIsNone(result.S)
        self.assertFalse(result.complete)

    def test_a_crash_scores_zero_even_with_a_submission(self) -> None:
        result = score(events(SUBMIT_EVENT, CRASH_EVENT), LIMITS, {"lint": True}, {"sva": True})
        self.assertEqual((result.S, result.V, result.O), (0, 0, 0))
        self.assertIn("crashed", result.reason)

    def test_a_refused_submission_is_not_a_submission(self) -> None:
        refused = [{"seq": 1, "tool": SUBMIT_EVENT, "resource": "x", "action": "deny", "rule": "default"}]
        result = score(refused, LIMITS, {"lint": True}, {"sva": True})
        self.assertEqual((result.S, result.V), (0, 0))
        self.assertIn("no permitted submission", result.reason)

    def test_no_submission_is_not_a_pass(self) -> None:
        result = score(events("fs-read", "fs-read"), LIMITS, {"lint": True}, {"sva": True})
        self.assertEqual(result.S, 0)
        self.assertIn("no permitted submission", result.reason)

    def test_one_failing_visible_gate_makes_v_zero(self) -> None:
        result = score(
            events(SUBMIT_EVENT), LIMITS, {"lint": True, "sim": False}, {"sva": True}
        )
        self.assertEqual((result.S, result.V, result.O), (1, 0, 1))
        self.assertIn("sim", result.reason)

    def test_a_gate_with_no_result_leaves_v_absent(self) -> None:
        result = score(
            events(SUBMIT_EVENT),
            LIMITS,
            {"lint": True},
            {"sva": True},
            expected_gates=["lint", "formal"],
        )
        self.assertIsNone(result.V)
        self.assertFalse(result.complete)
        self.assertIn("formal", result.reason)

    def test_a_missing_oracle_leaves_o_absent(self) -> None:
        result = score(events(SUBMIT_EVENT), LIMITS, {"lint": True}, None)
        self.assertIsNone(result.O)
        self.assertFalse(result.complete)

    def test_a_failing_oracle_component_makes_o_zero_while_v_stays_one(self) -> None:
        result = score(
            events(SUBMIT_EVENT), LIMITS, {"lint": True}, {"testbench": True, "sva": False}
        )
        self.assertEqual((result.V, result.O), (1, 0))


class TestBundle(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name: str, payload: dict | list) -> None:
        (self.root / name).write_text(json.dumps(payload), encoding="utf-8")

    def write_log(self, *tools: str) -> None:
        lines = [
            json.dumps({"seq": i, "tool": tool, "resource": "seq/B1_fifo/spec.md", "action": "allow", "rule": "read-workspace"})
            for i, tool in enumerate(tools, 1)
        ]
        (self.root / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def policy(self) -> Policy:
        self.write("policy.json", {"default": "deny", "rules": [
            {"id": "read-workspace", "action": "allow", "tool": "*", "resource": "**"}
        ]})
        return Policy.load(self.root / "policy.json")

    def test_a_complete_bundle_is_scored_and_reproduces_its_record(self) -> None:
        self.write("run.json", {"visible_gates": ["lint", "sim"], "budgets": {"tool_calls": 10}})
        self.write("gates.json", {"lint": True, "sim": True})
        self.write("oracle.json", {"testbench": True})
        self.write("outcome.json", {"S": 1, "V": 1, "O": 1})
        self.write_log("fs-read", SUBMIT_EVENT)

        result = report(load(self.root), self.policy())

        self.assertEqual(result.exit_code(), 0)
        self.assertTrue(result.reproduced)
        self.assertEqual(result.replay.matched, 2)

    def test_a_recorded_outcome_that_does_not_follow_is_reported(self) -> None:
        self.write("run.json", {"visible_gates": ["lint"], "budgets": {"tool_calls": 10}})
        self.write("gates.json", {"lint": True})
        self.write("oracle.json", {"testbench": True})
        self.write("outcome.json", {"S": 1, "V": 1, "O": 0})
        self.write_log(SUBMIT_EVENT)

        result = report(load(self.root))

        self.assertFalse(result.reproduced)
        self.assertEqual(result.exit_code(), 0, "the score is still the log's, not the record's")

    def test_a_diverged_decision_outranks_the_score(self) -> None:
        self.write("run.json", {"visible_gates": ["lint"], "budgets": {"tool_calls": 10}})
        self.write("gates.json", {"lint": True})
        self.write("oracle.json", {"testbench": True})
        # The log records a deny for a call the policy allows.
        (self.root / "events.jsonl").write_text(
            json.dumps({"seq": 1, "tool": "fs-read", "resource": "seq/B1_fifo/spec.md",
                        "action": "deny", "rule": "escape"}) + "\n",
            encoding="utf-8",
        )
        result = report(load(self.root), self.policy())
        self.assertEqual(result.exit_code(), 1)
        self.assertEqual(result.replay.diverged[0].seq, 1)

    def test_expected_budgets_drive_the_classification(self) -> None:
        self.write_log("fs-read", "fs-read")
        self.write("expected.json", {"visible_gates": [], "budgets": {"tool_calls": 1}})

        result = report(load(self.root))

        self.assertTrue(result.score.scored)
        self.assertEqual(result.score.S, 0)
        self.assertIn("exhausted", result.score.reason)

    def test_an_excluded_run_exits_two_and_is_not_a_zero(self) -> None:
        self.write("run.json", {"visible_gates": [], "budgets": {"tool_calls": 10}})
        self.write_log("infra")
        result = report(load(self.root))
        self.assertEqual(result.exit_code(), 2)
        self.assertFalse(result.score.scored)

    def test_an_incomplete_bundle_exits_three(self) -> None:
        self.write("run.json", {"visible_gates": ["lint", "formal"], "budgets": {"tool_calls": 10}})
        self.write("gates.json", {"lint": True})
        self.write_log(SUBMIT_EVENT)
        result = report(load(self.root))
        self.assertEqual(result.exit_code(), 3)

    def test_the_score_names_the_oracle_that_produced_o(self) -> None:
        self.write("run.json", {"visible_gates": ["lint"], "budgets": {"tool_calls": 10}})
        self.write("gates.json", {"lint": True})
        self.write(
            "oracle.json",
            {
                "scheme": "bendeda-oracle-result-v1",
                "host": "scoring-1",
                "commitment_root": "a9eb",
                "pack_version": "0.0.1-demo",
                "components": {"testbench": True},
            },
        )
        self.write_log(SUBMIT_EVENT)

        payload = report(load(self.root)).as_json()

        self.assertEqual(payload["O"], 1)
        self.assertEqual(payload["oracle"]["host"], "scoring-1")
        self.assertEqual(payload["oracle"]["pack_version"], "0.0.1-demo")
        self.assertEqual(payload["oracle"]["commitment_root"], "a9eb")

    def test_a_flat_oracle_file_has_no_provenance(self) -> None:
        # Hand-written `{name: bool}` results are still readable; they simply have no
        # scorer to name, and inventing one would be worse than saying nothing.
        self.write("oracle.json", {"testbench": True})
        self.write_log(SUBMIT_EVENT)
        self.assertNotIn("oracle", report(load(self.root)).as_json())

    def test_a_bundle_without_a_log_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            load(self.root)

    def test_a_non_boolean_gate_result_is_refused(self) -> None:
        self.write_log(SUBMIT_EVENT)
        self.write("gates.json", {"lint": "pass"})
        with self.assertRaises(ValueError):
            load(self.root)


if __name__ == "__main__":
    unittest.main()
