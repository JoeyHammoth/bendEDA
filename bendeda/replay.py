# SPDX-License-Identifier: Apache-2.0
"""Re-decide a run's audit log, so the log is evidence rather than testimony.

This replays the *proxy's* decisions, not a whole run: given `events.jsonl` and
the policy, every recorded decision must be the one the policy produces now. That
is the property a recorded run needs before anyone reads its result — either the
log and the policy agree, or the difference is printed with the sequence number
that diverged.

Two recorded decisions are not the policy's and must not be read as disagreements:
the proxy's ceiling refusal (`rule: budget`, written when the call count reaches the
allowance the run declared) and the harness's `infra` marker. The first is reproduced
from the allowance, the second is not a tool call at all — so a budget-exhausted run
can still be evidence, which `S=0` depends on.

Scoring is not here: gates, budgets and the `S=0`-versus-excluded call belong to
`score.py`. Re-deriving a score re-runs the gates, which needs the artifacts and
not just the decisions — so a scored outcome cannot be checked from the log alone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bendeda.budget import EXCLUDED_EVENT, Limits
from bendeda.proxy import Policy

#: The rule the proxy writes when it refuses a call for exceeding the allowance.
BUDGET_RULE = "budget"


@dataclass(frozen=True)
class Divergence:
    seq: int
    tool: str
    resource: str
    logged: str
    replayed: str
    rule_logged: str
    rule_replayed: str

    def render(self) -> str:
        return (
            f"seq {self.seq}: {self.tool} {self.resource} — logged {self.logged} "
            f"({self.rule_logged}), replayed {self.replayed} ({self.rule_replayed})"
        )


@dataclass
class ReplayReport:
    events: int = 0
    matched: int = 0
    malformed: list[str] = field(default_factory=list)
    diverged: list[Divergence] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.events > 0 and not self.diverged and not self.malformed

    def exit_code(self) -> int:
        """0 reproduced, 1 a difference, 3 nothing to replay."""
        if self.events == 0:
            return 3
        if self.diverged or self.malformed:
            return 1
        return 0

    def as_json(self) -> dict[str, Any]:
        return {
            "events": self.events,
            "matched": self.matched,
            "malformed": self.malformed,
            "diverged": [d.__dict__ for d in self.diverged],
            "ok": self.ok,
        }


def read_events(path: str | Path) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    problems: list[str] = []
    text = Path(path).read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"line {number}: invalid JSON ({exc})")
            continue
        if not isinstance(event, dict) or "tool" not in event or "resource" not in event:
            problems.append(f"line {number}: no tool/resource")
            continue
        events.append(event)
    return events, problems


def replay(
    events_path: str | Path,
    policy: Policy,
    limits: Limits | None = None,
) -> ReplayReport:
    """Every tool decision re-decided; the ceiling refusal re-derived from the allowance.

    `limits` is the allowance the run declared. Without it a `budget` denial cannot be
    checked at all, and this says so rather than reading the proxy's own ceiling as a
    policy disagreement — which it never was.
    """
    report = ReplayReport()
    events, problems = read_events(events_path)
    report.malformed.extend(problems)
    report.events = len(events)
    calls = 0
    for event in events:
        tool = str(event["tool"])
        resource = str(event["resource"])
        if tool == EXCLUDED_EVENT:
            # The harness wrote this when the sandbox failed; the policy never saw it.
            continue
        seen = calls
        calls += 1
        logged = str(event.get("action", ""))
        logged_rule = str(event.get("rule", ""))
        seq = int(event.get("seq", 0))
        if logged_rule == BUDGET_RULE:
            if limits is None:
                report.diverged.append(
                    Divergence(
                        seq=seq,
                        tool=tool,
                        resource=resource,
                        logged=logged or "(missing)",
                        replayed="(undecidable: no allowance declared)",
                        rule_logged=logged_rule,
                        rule_replayed=BUDGET_RULE,
                    )
                )
            elif logged == "deny" and seen >= limits.calls:
                report.matched += 1
            else:
                report.diverged.append(
                    Divergence(
                        seq=seq,
                        tool=tool,
                        resource=resource,
                        logged=logged or "(missing)",
                        replayed="allow",
                        rule_logged=logged_rule,
                        rule_replayed=f"budget not reached after {seen} call(s) of {limits.calls}",
                    )
                )
            continue
        decision = policy.decide(tool, resource)
        if logged == decision.action and logged_rule == decision.rule:
            report.matched += 1
            continue
        report.diverged.append(
            Divergence(
                seq=seq,
                tool=tool,
                resource=resource,
                logged=logged or "(missing)",
                replayed=decision.action,
                rule_logged=logged_rule or "(missing)",
                rule_replayed=decision.rule,
            )
        )
    return report
