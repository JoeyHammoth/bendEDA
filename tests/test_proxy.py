# SPDX-License-Identifier: Apache-2.0
"""The policy proxy and decision replay (issue #15, first increment).

Three properties are worth a test here, and they are the ones that would be
tempting to assert by eye: a deny cannot be shadowed by a broader allow, a path
that climbs out of the workspace cannot reach the oracle, and a log that no longer
matches its policy is reported at the sequence number that diverged.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from bendeda.proxy import AuditLog, Policy, handle_call, normalize_resource, serve
from bendeda.replay import replay

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "proxy"
NL = chr(10)


def policy() -> Policy:
    return Policy.load(FIXTURES / "policy.json")


class TestPolicy(unittest.TestCase):
    def test_a_read_is_allowed_by_the_rule_that_matches_it(self) -> None:
        decision = policy().decide("fs-read", "tasks/seq/B1_fifo/spec.md")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.rule, "read-workspace")

    def test_a_deny_cannot_be_shadowed_by_a_broader_allow(self) -> None:
        decision = policy().decide("fs-read", "oracle/b1_fifo/checks.md")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule, "deny-oracle")

    def test_a_write_outside_the_allowlist_falls_through_to_deny(self) -> None:
        decision = policy().decide("fs-write", "tasks/seq/B1_fifo/LAWS.bend")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule, "default")

    def test_a_write_the_policy_names_is_allowed(self) -> None:
        decision = policy().decide("fs-write", "tasks/seq/B1_fifo/model.bend")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.rule, "write-model")

    def test_a_path_that_climbs_out_of_the_workspace_is_refused(self) -> None:
        for resource in ("tasks/../oracle/x", "../oracle/x", "/oracle/x", "tasks/a/../../../etc/passwd"):
            decision = policy().decide("fs-read", resource)
            self.assertFalse(decision.allowed, resource)

    def test_a_path_that_climbs_back_inside_is_resolved_not_refused(self) -> None:
        # `oracle/./x/../../y` normalises to `y`, which is inside the workspace;
        # refusing it would be over-strict, and it must not match `oracle/**`.
        decision = policy().decide("fs-read", "oracle/./x/../../y")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.rule, "read-workspace")

    def test_network_egress_is_allowlisted_by_host(self) -> None:
        self.assertTrue(policy().decide("net", "github.com/bendlang/bend").allowed)
        self.assertEqual(policy().decide("net", "example.com/x").rule, "default")

    def test_normalisation_keeps_a_plain_relative_path(self) -> None:
        self.assertEqual(normalize_resource("./tasks//a/./b.bend"), "tasks/a/b.bend")
        self.assertIsNone(normalize_resource("C:/Windows/system32"))
        self.assertIsNone(normalize_resource("C:Windows"))


class TestAuditLog(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.events = Path(self.tmp.name) / "events.jsonl"
        self.log = AuditLog(self.events)

    def test_every_decision_is_one_append_only_line(self) -> None:
        handle_call(policy(), self.log, {"tool": "fs-read", "resource": "tasks/a"})
        handle_call(policy(), self.log, {"tool": "fs-read", "resource": "oracle/a"})
        lines = self.events.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        first, second = (json.loads(line) for line in lines)
        self.assertEqual((first["seq"], first["allowed"], first["rule"]), (1, True, "read-workspace"))
        self.assertEqual((second["seq"], second["allowed"], second["rule"]), (2, False, "deny-oracle"))

    def test_a_denied_call_answers_403_and_a_malformed_one_400(self) -> None:
        self.assertEqual(handle_call(policy(), self.log, {"tool": "fs-read", "resource": "oracle/a"})[0], 403)
        self.assertEqual(handle_call(policy(), self.log, {"tool": "fs-read"})[0], 400)
        self.assertEqual(handle_call(policy(), self.log, ["fs-read", "tasks/a"])[0], 400)
        # A malformed request is not a decision, so it is not logged as one.
        self.assertEqual(len(self.events.read_text(encoding="utf-8").splitlines()), 1)


class TestServer(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = AuditLog(Path(self.tmp.name) / "events.jsonl")
        self.server = serve(policy(), self.log, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def call(self, tool: str, resource: str) -> tuple[int, dict]:
        body = json.dumps({"tool": tool, "resource": resource}).encode("utf-8")
        request = urllib.request.Request(
            self.base + "/call", data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_the_endpoint_answers_allow_and_deny(self) -> None:
        status, body = self.call("fs-read", "tasks/a")
        self.assertEqual(status, 200)
        self.assertTrue(body["decision"]["allowed"])
        status, body = self.call("fs-read", "oracle/a")
        self.assertEqual(status, 403)
        self.assertFalse(body["decision"]["allowed"])

    def test_the_endpoint_writes_what_it_answered(self) -> None:
        self.call("fs-read", "tasks/a")
        self.call("net", "example.com/x")
        events = [json.loads(line) for line in self.log.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([event["allowed"] for event in events], [True, False])

    def test_health_reports_the_default(self) -> None:
        with urllib.request.urlopen(self.base + "/health", timeout=10) as response:
            body = json.loads(response.read())
        self.assertEqual(body["default"], "deny")
        self.assertEqual(body["rules"], 4)


class TestReplay(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.events = Path(self.tmp.name) / "events.jsonl"

    def record(self, calls: list[tuple[str, str]]) -> None:
        log = AuditLog(self.events)
        for tool, resource in calls:
            handle_call(policy(), log, {"tool": tool, "resource": resource})

    def test_a_log_from_the_same_policy_reproduces(self) -> None:
        self.record([("fs-read", "tasks/a"), ("fs-read", "oracle/a"), ("net", "example.com")])
        report = replay(self.events, policy())
        self.assertEqual(report.exit_code(), 0, report.as_json())
        self.assertEqual((report.events, report.matched), (3, 3))

    def test_a_changed_policy_is_reported_at_the_sequence_that_diverged(self) -> None:
        self.record([("fs-write", "tasks/seq/B1_fifo/model.bend")])
        strict = Policy.load(FIXTURES / "policy.json")
        strict.rules = tuple(
            rule for rule in strict.rules if rule.id != "write-model"
        )
        report = replay(self.events, strict)
        self.assertEqual(report.exit_code(), 1)
        self.assertEqual(len(report.diverged), 1)
        self.assertEqual(report.diverged[0].seq, 1)
        self.assertEqual(report.diverged[0].replayed, "deny")

    def test_an_empty_log_is_not_a_pass(self) -> None:
        self.events.write_text("", encoding="utf-8")
        report = replay(self.events, policy())
        self.assertEqual(report.exit_code(), 3)
        self.assertFalse(report.ok)

    def record_budget(self, calls: int, allowance: int) -> None:
        log = AuditLog(self.events)
        for number in range(calls):
            handle_call(policy(), log, {"tool": "fs-read", "resource": f"tasks/{number}"}, allowance)

    def test_a_budget_refusal_is_reproduced_from_the_declared_allowance(self) -> None:
        from bendeda.budget import Limits

        self.record_budget(calls=3, allowance=1)  # one call, then two refusals
        report = replay(self.events, policy(), Limits(calls=1))
        self.assertEqual(report.exit_code(), 0, report.as_json())
        self.assertEqual((report.events, report.matched), (3, 3))

    def test_an_allowance_that_was_not_reached_is_a_divergence(self) -> None:
        from bendeda.budget import Limits

        self.record_budget(calls=3, allowance=1)
        report = replay(self.events, policy(), Limits(calls=5))
        self.assertEqual(report.exit_code(), 1)
        self.assertEqual([party.seq for party in report.diverged], [2, 3])
        self.assertIn("budget not reached", report.diverged[0].rule_replayed)

    def test_a_budget_refusal_without_an_allowance_is_undecidable(self) -> None:
        self.record_budget(calls=2, allowance=1)
        report = replay(self.events, policy())
        self.assertEqual(report.exit_code(), 1, "it cannot be vouched for, so it is not a pass")
        self.assertIn("undecidable", report.diverged[0].replayed)

    def test_an_infra_marker_is_not_a_tool_decision(self) -> None:
        # The harness writes this line when the sandbox fails; the proxy never saw it.
        self.events.write_text(
            '{"seq": 0, "tool": "infra", "resource": "daemon died"}' + NL,
            encoding="utf-8",
        )
        report = replay(self.events, policy())
        self.assertEqual(report.diverged, [])
        self.assertEqual(report.matched, 0)

    def test_a_malformed_line_is_reported_rather_than_skipped(self) -> None:
        self.events.write_text('{"tool": "fs-read", "resource": "tasks/a", "action": "allow", "rule": "read-workspace"}'
                               + NL + "not json" + NL, encoding="utf-8")
        report = replay(self.events, policy())
        self.assertEqual(report.exit_code(), 1)
        self.assertEqual(len(report.malformed), 1)
        self.assertEqual(report.matched, 1)


if __name__ == "__main__":
    unittest.main()
