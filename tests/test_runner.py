# SPDX-License-Identifier: Apache-2.0
"""The runner's checks, and the budget classification (issue #15).

No Docker here: the two checks take a `run` function, so the inspection JSON is the
input and the assertions are about the verdict rather than about a daemon being up.
The real daemon is exercised separately in docs/policy-proxy.md.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bendeda.budget import Limits, Outcome, classify, read_log
from bendeda.runner import AgentSpec, Unrunnable, check, plan

NL = chr(10)


def inspector(container: dict, network: dict) -> object:
    def run(argv):
        if argv[1] == "inspect":
            return 0, json.dumps([container])
        return 0, json.dumps([network])

    return run


def container_json(workspace: Path, network: str = "bendeda-offline", extra: list | None = None) -> dict:
    mounts = [{"Source": str(workspace), "Destination": "/work"}]
    mounts.extend(extra or [])
    return {
        "Mounts": mounts,
        "NetworkSettings": {"Networks": {network: {"Gateway": ""}}},
    }


INTERNAL = {"Internal": True, "Name": "bendeda-offline"}
EXPOSED = {"Internal": False, "Name": "bendeda-offline"}


class TestPlan(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.spec = AgentSpec(
            workspace=self.root,
            policy=self.root / "policy.json",
            events=self.root / "run" / "events.jsonl",
        )

    def test_the_agent_plan_mounts_only_the_workspace(self) -> None:
        agent = plan(self.spec)[-1]
        mounts = [agent[i + 1] for i, part in enumerate(agent) if part == "--mount"]
        self.assertEqual(len(mounts), 1)
        self.assertIn("target=/work", mounts[0])
        self.assertNotIn("oracle", " ".join(agent))

    def test_the_plan_creates_an_internal_network_and_the_proxy(self) -> None:
        network, proxy, _agent = plan(self.spec)
        self.assertEqual(network[:4], ["docker", "network", "create", "--internal"])
        self.assertIn("proxy", proxy)
        self.assertIn("--events", proxy)

    def test_a_plan_without_a_policy_is_refused(self) -> None:
        self.assertRaises(Unrunnable, plan, AgentSpec(workspace=self.root))


class TestCheck(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "work"
        self.workspace.mkdir()
        self.oracle = self.root / "oracle"
        self.oracle.mkdir()

    def test_a_clean_container_has_no_problems(self) -> None:
        problems = check(
            "agent", "bendeda-offline", self.workspace, self.oracle,
            inspector(container_json(self.workspace), INTERNAL),
        )
        self.assertEqual(problems, [])

    def test_a_network_with_a_gateway_is_a_problem(self) -> None:
        problems = check(
            "agent", "bendeda-offline", self.workspace, None,
            inspector(container_json(self.workspace), EXPOSED),
        )
        self.assertTrue(any("not internal" in problem for problem in problems), problems)

    def test_an_extra_mount_is_a_problem(self) -> None:
        extra = [{"Source": str(self.oracle), "Destination": "/oracle"}]
        problems = check(
            "agent", "bendeda-offline", self.workspace, self.oracle,
            inspector(container_json(self.workspace, extra=extra), INTERNAL),
        )
        self.assertTrue(any("expected exactly" in problem for problem in problems), problems)
        self.assertTrue(any("oracle is reachable" in problem for problem in problems), problems)

    def test_the_same_mount_reported_the_msys_way_still_matches(self) -> None:
        # Docker Desktop on Windows reports the source as /c/Users/... on some
        # calls and C:/Users/... on others; a raw comparison invents a problem.
        # The normaliser is pure, so this holds on every platform.
        from bendeda.runner import _normalise_source

        self.assertEqual(
            _normalise_source("/c/Users/Me/work"), _normalise_source("C:/Users/Me/work")
        )
        self.assertNotEqual(
            _normalise_source("/c/Users/Me/work"), _normalise_source("C:/Users/You/work")
        )

    def test_host_networking_is_named(self) -> None:
        container = container_json(Path("placeholder"))
        container["NetworkSettings"]["Networks"] = {"host": {}}
        problems = check(
            "agent", "bendeda-offline", self.workspace, None,
            inspector(container, INTERNAL),
        )
        self.assertTrue(any("host networking" in problem for problem in problems), problems)


class TestBudget(unittest.TestCase):
    def test_within_budget_is_scored_by_the_gates(self) -> None:
        outcome = classify([{"tool": "fs-read"}], Limits(calls=10))
        self.assertTrue(outcome.scored)
        self.assertIsNone(outcome.score)

    def test_exhaustion_is_scored_zero_not_excluded(self) -> None:
        events = [{"tool": "fs-read"} for _ in range(11)]
        outcome = classify(events, Limits(calls=10))
        self.assertEqual((outcome.scored, outcome.score), (True, 0.0), outcome)

    def test_an_infrastructure_failure_is_excluded_even_when_exhausted(self) -> None:
        events = [{"tool": "fs-read"} for _ in range(11)] + [{"tool": "infra", "reason": "daemon died"}]
        outcome = classify(events, Limits(calls=10))
        self.assertFalse(outcome.scored)
        self.assertIsNone(outcome.score)
        self.assertIn("daemon died", outcome.reason)

    def test_the_outcome_serialises(self) -> None:
        self.assertEqual(
            Outcome.excluded("boom", 3).as_json(),
            {"scored": False, "score": None, "reason": "boom", "calls": 3},
        )

    def test_reading_a_log_rejects_a_bad_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text('{"tool": "fs-read"}' + NL + "nope" + NL, encoding="utf-8")
            self.assertRaises(ValueError, read_log, path)


if __name__ == "__main__":
    unittest.main()
