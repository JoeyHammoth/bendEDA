# SPDX-License-Identifier: Apache-2.0
"""`S`, `V` and `O` for a recorded run (issue #15).

The design document defines the three verdicts (§5.4): `S` is 1 iff the agent
submitted before budget exhaustion or a crash; `V` is 1 iff `S` is 1 and every gate
in the arm's visible set passes on the submitted artifacts; `O` is 1 iff `S` is 1 and
every oracle component passes. An infrastructure failure does not score zero — it
voids the run, which is re-run and recorded in `run.json.excluded`.

What is replayed here is the *outcome*, not the tool results. The audit log is
re-decided against its policy, `S` is recomputed from the events, and `V`/`O` come
from the results the harness recorded for the submitted artifacts. A gate with no
recorded result is **not** a pass: the verdict stays absent, the run is incomplete,
and the CLI exits 3 rather than printing a zero somebody would average.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from bendeda import replay as replay_module
from bendeda.budget import Limits, classify, read_log
from bendeda.proxy import Policy

SUBMIT_EVENT = "submit"
CRASH_EVENT = "crash"


@dataclass(frozen=True)
class Score:
    scored: bool
    S: int | None
    V: int | None
    O: int | None
    reason: str

    @property
    def complete(self) -> bool:
        return self.scored and None not in (self.S, self.V, self.O)

    def as_json(self) -> dict[str, Any]:
        return {
            "scored": self.scored,
            "S": self.S,
            "V": self.V,
            "O": self.O,
            "complete": self.complete,
            "reason": self.reason,
        }


def _verdict(
    results: Mapping[str, bool] | None,
    expected: Sequence[str] | None,
    noun: str,
) -> tuple[int | None, str]:
    """A verdict, or `None` when the results cannot support one.

    Missing results are the interesting case: `all([])` is true, so a plain `all()`
    turns an unrecorded gate into a silent pass. Comparing against the arm's declared
    set first is what makes a partial record incomplete instead of green.
    """
    if results is None:
        return None, f"no {noun} results recorded"
    if expected is not None:
        missing = sorted(set(expected) - set(results))
        if missing:
            return None, f"no result for {', '.join(missing)}"
    if not results:
        return 1, f"the {noun} set is empty, so the condition is vacuous"
    failed = sorted(name for name, ok in results.items() if not ok)
    if failed:
        return 0, f"{noun} failed: {', '.join(failed)}"
    return 1, f"all {len(results)} {noun} passed"


def score(
    events: Sequence[dict[str, Any]],
    limits: Limits,
    gates: Mapping[str, bool] | None = None,
    oracle: Mapping[str, bool] | None = None,
    expected_gates: Sequence[str] | None = None,
) -> Score:
    """The three verdicts, with exclusion taking the run out of the score entirely."""
    outcome = classify(events, limits)
    if not outcome.scored:
        return Score(False, None, None, None, outcome.reason)
    if outcome.score is not None:
        # Exhaustion is a result: the arm spent its allowance, so S=0 and V=O=0.
        return Score(True, 0, 0, 0, outcome.reason)
    if any(event.get("tool") == CRASH_EVENT for event in events):
        return Score(True, 0, 0, 0, "the agent crashed before submitting")
    if not any(event.get("tool") == SUBMIT_EVENT for event in events):
        return Score(True, 0, 0, 0, "no submission was recorded before the log ended")

    visible, visible_reason = _verdict(gates, expected_gates, "visible gates")
    oracle_verdict, oracle_reason = _verdict(oracle, None, "oracle components")
    return Score(
        True,
        1,
        visible,
        oracle_verdict,
        f"submitted; {visible_reason}; {oracle_reason}",
    )


@dataclass(frozen=True)
class Bundle:
    """One run's directory: what was configured, what happened, what was judged."""

    root: Path
    run: dict[str, Any]
    events: list[dict[str, Any]]
    gates: dict[str, bool] | None
    oracle: dict[str, bool] | None
    recorded: dict[str, Any] | None

    @property
    def limits(self) -> Limits:
        budgets = self.run.get("budgets") or {}
        return Limits(calls=int(budgets.get("tool_calls", 400)))

    @property
    def expected_gates(self) -> list[str] | None:
        gates = self.run.get("visible_gates")
        return [str(name) for name in gates] if isinstance(gates, list) else None


def _booleans(path: Path, key: str) -> dict[str, bool] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: expected an object, got {type(data).__name__}")
    values = data.get(key, data)
    if not isinstance(values, dict):
        raise ValueError(f"{path.name}: {key} must be an object of name -> boolean")
    out: dict[str, bool] = {}
    for name, ok in values.items():
        if not isinstance(ok, bool):
            raise ValueError(f"{path.name}: {name} is {type(ok).__name__}, not a boolean")
        out[str(name)] = ok
    return out


def load(root: str | Path) -> Bundle:
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"not a run bundle: {root}")
    events_path = root / "events.jsonl"
    if not events_path.is_file():
        raise ValueError(f"no events.jsonl in {root}; a run without a tool log cannot be scored")
    run: dict[str, Any] = {}
    run_path = root / "run.json"
    if run_path.is_file():
        data = json.loads(run_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("run.json: expected an object")
        run = data
    recorded: dict[str, Any] | None = None
    outcome_path = root / "outcome.json"
    if outcome_path.is_file():
        data = json.loads(outcome_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("outcome.json: expected an object")
        recorded = data
    return Bundle(
        root=root,
        run=run,
        events=read_log(events_path),
        gates=_booleans(root / "gates.json", "gates"),
        oracle=_booleans(root / "oracle.json", "components"),
        recorded=recorded,
    )


@dataclass(frozen=True)
class ScoreReport:
    score: Score
    replay: replay_module.ReplayReport | None
    reproduced: bool | None
    notes: tuple[str, ...] = ()

    def as_json(self) -> dict[str, Any]:
        payload = self.score.as_json()
        payload["replay"] = self.replay.as_json() if self.replay is not None else None
        payload["outcome_reproduced"] = self.reproduced
        if self.notes:
            payload["notes"] = list(self.notes)
        return payload

    def exit_code(self) -> int:
        """0 scored, 1 decisions diverged, 2 excluded (re-run), 3 incomplete."""
        if self.replay is not None and not self.replay.ok:
            return 1
        if not self.score.scored:
            return 2
        if not self.score.complete:
            return 3
        return 0


def report(bundle: Bundle, policy: Policy | None = None) -> ScoreReport:
    """Replay the decisions, recompute the verdicts, and compare with what was recorded."""
    replayed = None
    notes: list[str] = []
    if policy is not None:
        replayed = replay_module.replay(bundle.root / "events.jsonl", policy)
        if not replayed.ok:
            notes.append("the tool log does not follow from its policy, so the outcome is not evidence")
    scored = score(
        bundle.events,
        bundle.limits,
        bundle.gates,
        bundle.oracle,
        bundle.expected_gates,
    )
    reproduced: bool | None = None
    if bundle.recorded is not None:
        reproduced = all(
            bundle.recorded.get(key) == getattr(scored, key) for key in ("S", "V", "O")
        )
        if not reproduced:
            notes.append("the recorded outcome does not follow from the log")
    return ScoreReport(scored, replayed, reproduced, tuple(notes))
