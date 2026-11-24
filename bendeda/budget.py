# SPDX-License-Identifier: Apache-2.0
"""Budgets, and the distinction issue #15 insists on.

An exhausted budget is a *result*: the arm used its allowance and scored zero. An
infrastructure failure is not a result: the run is excluded and re-run. Collapsing
the two is how a broken harness becomes a finding, so the classification is code with
one exit door per case rather than a convention in a notebook.

The score itself comes from the gates; this module only decides whether a run has one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

EXCLUDED_EVENT = "infra"


@dataclass(frozen=True)
class Limits:
    calls: int = 400


@dataclass(frozen=True)
class Outcome:
    scored: bool
    score: float | None
    reason: str
    calls: int

    @classmethod
    def excluded(cls, reason: str, calls: int) -> Outcome:
        return cls(scored=False, score=None, reason=reason, calls=calls)

    @classmethod
    def exhausted(cls, calls: int) -> Outcome:
        return cls(scored=True, score=0.0, reason=f"budget exhausted after {calls} calls", calls=calls)

    @classmethod
    def within_budget(cls, calls: int) -> Outcome:
        return cls(scored=True, score=None, reason="within budget; the gates score it", calls=calls)

    def as_json(self) -> dict[str, Any]:
        return {"scored": self.scored, "score": self.score, "reason": self.reason, "calls": self.calls}


def classify(events: Iterable[dict[str, Any]], limits: Limits) -> Outcome:
    """Excluded beats exhausted: an infrastructure failure invalidates the budget too."""
    events = list(events)
    calls = sum(1 for event in events if event.get("tool") != EXCLUDED_EVENT)
    for event in events:
        if event.get("tool") == EXCLUDED_EVENT:
            detail = str(event.get("reason") or event.get("resource") or "unstated")
            return Outcome.excluded(f"infrastructure failure: {detail}", calls)
    if calls > limits.calls:
        return Outcome.exhausted(calls)
    return Outcome.within_budget(calls)


def count_calls(path: str | Path) -> int:
    """Calls seen so far, tolerating a line the proxy is still writing.

    The enforcement loop polls this file while the proxy appends to it, so a partial
    final line is expected rather than exceptional. `read_log` stays strict, because a
    *finished* log with a broken line is a different claim than a log still growing.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return 0
    calls = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("tool") != EXCLUDED_EVENT:
            calls += 1
    return calls


def read_log(path: str | Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {number}: invalid JSON ({exc})") from exc
        if not isinstance(event, dict):
            raise ValueError(f"line {number}: not an object")
        events.append(event)
    return events
