# SPDX-License-Identifier: Apache-2.0
"""The runner's checks, and the budget classification (issue #15).

No Docker here: the two checks take a `run` function, so the inspection JSON is the
input and the assertions are about the verdict rather than about a daemon being up.
The real daemon is exercised separately in docs/policy-proxy.md.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from bendeda.budget import Limits, Outcome, classify, read_log
from bendeda.runner import (
    AgentSpec,
    Unrunnable,
    check,
    enforce,
    exec_enforced,
    plan,
)

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

    def test_the_proxy_runs_as_the_invoking_user(self) -> None:
        """The events directory is the caller's, so a fixed image uid cannot write it."""
        from unittest import mock

        with mock.patch("bendeda.runner.os.getuid", return_value=1001, create=True), \
                mock.patch("bendeda.runner.os.getgid", return_value=1001, create=True):
            proxy = plan(self.spec)[1]
        self.assertEqual(proxy[proxy.index("-u") + 1], "1001:1001")

    def test_the_arm_also_runs_as_the_invoking_user(self) -> None:
        """The workspace is the caller's mount; the arm writes its artifacts into it."""
        from unittest import mock

        with mock.patch("bendeda.runner.os.getuid", return_value=1001, create=True), \
                mock.patch("bendeda.runner.os.getgid", return_value=1001, create=True):
            _network, proxy, agent = plan(self.spec)
        self.assertEqual(agent[agent.index("-u") + 1], "1001:1001")
        self.assertEqual(proxy[proxy.index("-u") + 1], "1001:1001")

    def test_a_host_without_a_uid_passes_none(self) -> None:
        """Windows has no uid; Docker's own image user is the only option there."""
        from unittest import mock

        with mock.patch("bendeda.runner.hasattr", return_value=False, create=True):
            _network, proxy, agent = plan(self.spec)
        self.assertNotIn("-u", proxy)
        self.assertNotIn("-u", agent)

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


class TestProxyBudget(unittest.TestCase):
    def test_the_call_after_the_allowance_is_refused_and_logged(self) -> None:
        from bendeda.proxy import AuditLog, Policy, Rule, handle_call

        with tempfile.TemporaryDirectory() as raw:
            log = AuditLog(Path(raw) / "events.jsonl")
            policy = Policy([Rule("read", "allow", "fs-*", "**")])
            first = handle_call(policy, log, {"tool": "fs-read", "resource": "a"}, max_calls=1)
            second = handle_call(policy, log, {"tool": "fs-read", "resource": "b"}, max_calls=1)

            self.assertEqual(first[0], 200)
            self.assertEqual(second[0], 429)
            self.assertEqual(second[1]["decision"]["rule"], "budget")
            self.assertEqual(log.calls(), 2, "a refused call is still a call in the log")
            self.assertEqual(classify(read_log(log.path), Limits(calls=1)).score, 0.0)


class FakeProcess:
    """A process that only exits when `stopped` is set, like a container being killed."""

    def __init__(self, code: int = 0, output: str = "ok", stopped: bool = False) -> None:
        self.code = code
        self.output = output
        self.stopped = stopped

    def poll(self):
        return self.code if self.stopped else None

    def communicate(self):
        return self.output, ""


class TestEnforcement(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.events = Path(self.tmp.name) / "events.jsonl"

    def write(self, count: int) -> None:
        lines = [
            json.dumps({"seq": i, "tool": "fs-read", "resource": f"f{i}"})
            for i in range(1, count + 1)
        ]
        self.events.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def test_the_allowance_is_enforced_while_the_command_runs(self) -> None:
        self.write(2)
        process = FakeProcess()
        killed: list[bool] = []

        result = enforce(
            process,
            self.events,
            max_calls=1,
            stop=lambda: killed.append(True),
            sleep=lambda seconds: None,
        )

        self.assertTrue(result.exhausted)
        self.assertEqual(result.stopped, "calls")
        self.assertEqual(result.calls, 2)
        self.assertEqual(killed, [True])

    def test_a_command_within_budget_is_not_stopped(self) -> None:
        self.write(1)
        result = enforce(
            FakeProcess(code=3, stopped=True), self.events, max_calls=1, sleep=lambda s: None
        )
        self.assertFalse(result.exhausted)
        self.assertEqual(result.code, 3, "the command's own exit status survives")

    def test_infrastructure_events_are_not_calls(self) -> None:
        self.events.write_text(
            json.dumps({"seq": 1, "tool": "infra", "resource": "daemon"}) + "\n",
            encoding="utf-8",
        )
        result = enforce(
            FakeProcess(stopped=True), self.events, max_calls=0, sleep=lambda s: None
        )
        self.assertFalse(result.exhausted)
        self.assertEqual(result.calls, 0)

    def test_the_wall_clock_stops_a_silent_command(self) -> None:
        self.write(0)
        ticks = iter([0, 0, 3600])
        result = enforce(
            FakeProcess(),
            self.events,
            max_calls=10,
            wall_min=1,
            clock=lambda: next(ticks),
            sleep=lambda seconds: None,
        )
        self.assertTrue(result.exhausted)
        self.assertEqual(result.stopped, "wall clock")

    def test_a_partial_line_is_not_counted_as_a_call(self) -> None:
        self.events.write_text('{"seq": 1, "tool": "fs-rea', encoding="utf-8")
        result = enforce(
            FakeProcess(stopped=True), self.events, max_calls=0, sleep=lambda s: None
        )
        self.assertEqual(result.calls, 0)

    def test_exec_enforced_kills_the_container(self) -> None:
        self.write(2)
        process = FakeProcess()
        calls: list[list[str]] = []

        def run(argv):
            calls.append(list(argv))
            return 0, ""

        result = exec_enforced(
            "bendeda-agent",
            ["python", "-m", "bendeda", "--version"],
            self.events,
            max_calls=1,
            spawn=lambda argv: process,
            run=run,
            sleep=lambda seconds: None,
        )

        self.assertTrue(result.exhausted)
        self.assertIn(["docker", "kill", "bendeda-agent"], calls)


class TestStaleImage(unittest.TestCase):
    """A harness image that carries a different package than this checkout."""

    def test_the_checkout_matches_itself(self) -> None:
        from bendeda.runner import package_fingerprint, stale_image

        fingerprint = package_fingerprint()
        problem = stale_image(
            "bendeda/harness:test-same", lambda argv: (0, fingerprint + NL)
        )
        self.assertIsNone(problem)

    def test_a_different_package_names_the_rebuild(self) -> None:
        from bendeda.runner import stale_image

        problem = stale_image("bendeda/harness:test-old", lambda argv: (0, "0" * 64 + NL))
        self.assertIsNotNone(problem)
        assert problem is not None
        self.assertIn("rebuild", problem)

    def test_an_image_without_the_package_is_a_problem_not_a_pass(self) -> None:
        from bendeda.runner import stale_image

        problem = stale_image("bendeda/harness:test-bare", lambda argv: (1, "no module" + NL))
        self.assertIsNotNone(problem)
        assert problem is not None
        self.assertIn("could not read", problem)

    def test_the_probe_is_one_command_and_runs_offline(self) -> None:
        from bendeda.runner import stale_image

        seen: list[list[str]] = []

        def run(argv):
            seen.append(list(argv))
            return 1, "no"

        stale_image("bendeda/harness:test-argv", run)
        self.assertEqual(seen[0][:3], ["docker", "run", "--rm"])
        self.assertIn("--network", seen[0])
        self.assertIn("none", seen[0])


class TestWallClockStopsRealWork(unittest.TestCase):
    """`--wall-min` against a command that really sleeps, not an injected clock.

    The injected-clock test above pins the arithmetic; this one pins the behaviour,
    because an allowance that only exists inside a fake clock is not an allowance.
    """

    def test_a_sleeping_command_is_stopped_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            events = Path(tmp) / "events.jsonl"
            events.write_text("", encoding="utf-8")
            process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            self.addCleanup(lambda: process.poll() is None and process.kill())
            started = time.monotonic()
            result = enforce(
                process,
                events,
                max_calls=100,
                # 0.02 minutes is 1.2 seconds: short enough to test, long enough that a
                # real scheduler pause does not make the assertion about the clock.
                wall_min=0.02,
                stop=process.kill,
                sleep=time.sleep,
                poll_s=0.05,
            )
            elapsed = time.monotonic() - started

        self.assertTrue(result.exhausted)
        self.assertEqual(result.stopped, "wall clock")
        self.assertIsNotNone(process.poll(), "the sleeping command was actually stopped")
        self.assertLess(elapsed, 15.0, f"took {elapsed:.1f}s to enforce a 1.2s allowance")


class TestTimeouts(unittest.TestCase):
    """A hung command is a failed step that leaves no container behind.

    Killing the `docker` client stops the client and nothing else: the daemon's process
    keeps running, and it keeps the bind mount busy. A calibration entry must not be
    able to sit there for longer than its timeout.
    """

    def test_a_named_container_is_read_from_the_argv(self) -> None:
        from bendeda.runner import _named_container

        self.assertEqual(
            _named_container(["docker", "run", "-d", "--name", "bendeda-agent", "img"]),
            "bendeda-agent",
        )
        self.assertIsNone(_named_container(["docker", "ps"]))
        self.assertIsNone(_named_container(["docker", "run", "--name"]))

    def test_a_hung_command_is_a_failed_step_that_kills_its_container(self) -> None:
        from bendeda.runner import _run

        killed: list[str] = []
        code, output = _run(
            [sys.executable, "-c", "import time; time.sleep(30)", "--name", "bendeda-hung"],
            timeout=0.5,
            kill=killed.append,
        )

        self.assertEqual(code, 1)
        self.assertIn("timed out", output)
        self.assertEqual(killed, ["bendeda-hung"])

    def test_an_unnamed_timeout_kills_nothing(self) -> None:
        from bendeda.runner import _run

        killed: list[str] = []
        code, _output = _run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=0.5,
            kill=killed.append,
        )

        self.assertEqual((code, killed), (1, []))


if __name__ == "__main__":
    unittest.main()
