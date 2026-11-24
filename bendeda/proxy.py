# SPDX-License-Identifier: Apache-2.0
"""The policy proxy: the only egress an agent container may use (issue #15).

Why a process and not a library: a rule the agent calls is a rule the agent can
decline to call. The thing that is checked is the socket, so the decision has to
live in whatever holds the socket. Nothing here claims the container is sandboxed
yet — that is the part of #15 that needs a runtime, and saying so is cheaper than
implying it.

What is implemented: a deny-by-default policy over (tool, resource), an
append-only audit log of every decision, an HTTP endpoint that answers allow or
deny, a per-arm call budget that is refused here rather than noticed by a
supervisor afterwards, and a replay that re-decides a log so a recorded run can be
checked without being trusted.

What is not implemented: the container plumbing that makes this the only route
out, and the scoring of what a refusal means (that is `score.py`, not a decision).
"""

from __future__ import annotations

import fnmatch
import json
import posixpath
import re
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable

from bendeda.budget import EXCLUDED_EVENT

ALLOW = "allow"
DENY = "deny"
ACTIONS = (ALLOW, DENY)
_DRIVE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class Rule:
    id: str
    action: str
    tool: str
    resource: str
    reason: str = ""


@dataclass(frozen=True)
class Decision:
    action: str
    rule: str
    reason: str

    @property
    def allowed(self) -> bool:
        return self.action == ALLOW

    def as_json(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "allowed": self.allowed,
            "rule": self.rule,
            "reason": self.reason,
        }


def normalize_resource(resource: str) -> str | None:
    """A workspace-relative POSIX path, or None when it leaves the workspace.

    The globs are textual, so `tasks/../oracle/x` would otherwise match
    `tasks/**` and reach the oracle. Normalising before matching is what makes the
    path rules mean what they say.
    """
    text = resource.replace("\\", "/").strip()
    if not text:
        return None
    while text.startswith("./"):
        text = text[2:]
    # `/x`, `C:/x` and `C:x` are all outside the workspace; only a relative path
    # is addressed by these globs.
    if text.startswith("/") or _DRIVE.match(text):
        return None
    normal = posixpath.normpath(text)
    if normal in (".", "..") or normal.startswith("../"):
        return None
    return normal


class Policy:
    def __init__(self, rules: Iterable[Rule], default: str = DENY) -> None:
        if default not in ACTIONS:
            raise ValueError(f"default must be one of {ACTIONS}, not {default!r}")
        self.rules = tuple(rules)
        self.default = default

    @classmethod
    def load(cls, path: str | Path) -> Policy:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rules: list[Rule] = []
        for raw in data.get("rules", []):
            action = raw.get("action")
            if action not in ACTIONS:
                raise ValueError(f"rule {raw.get('id', '?')}: action must be one of {ACTIONS}")
            rules.append(
                Rule(
                    id=str(raw["id"]),
                    action=action,
                    tool=str(raw.get("tool", "*")),
                    resource=str(raw.get("resource", "*")),
                    reason=str(raw.get("reason", "")),
                )
            )
        return cls(rules, str(data.get("default", DENY)))

    def decide(self, tool: str, resource: str) -> Decision:
        """Deny wins: every deny rule is tried before any allow rule.

        A more specific allow cannot override a deny. That makes a policy
        authorable without a precedence puzzle, and the cost is that exceptions to
        a deny need the deny narrowed rather than shadowed.
        """
        target = normalize_resource(resource)
        if target is None:
            return Decision(DENY, "escape", "resource is outside the workspace root")
        ordered = [rule for rule in self.rules if rule.action == DENY] + [
            rule for rule in self.rules if rule.action == ALLOW
        ]
        for rule in ordered:
            if fnmatch.fnmatchcase(tool, rule.tool) and fnmatch.fnmatchcase(target, rule.resource):
                return Decision(rule.action, rule.id, rule.reason or f"matched rule {rule.id}")
        return Decision(self.default, "default", f"no rule matched {tool}:{target}")


class AuditLog:
    """Append-only JSONL. One line per decision, whether or not it was allowed."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seq = 0
        self._calls = 0

    def calls(self) -> int:
        """Calls recorded so far, in the units a budget is measured in.

        Infrastructure events are not calls, which is the same rule `budget.classify`
        applies; the two must agree or the proxy would refuse work the log then calls
        within budget.
        """
        return self._calls

    def record(self, tool: str, resource: str, decision: Decision) -> dict[str, Any]:
        self._seq += 1
        if tool != EXCLUDED_EVENT:
            self._calls += 1
        event: dict[str, Any] = {"seq": self._seq, "tool": tool, "resource": resource}
        event.update(decision.as_json())
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        return event


def handle_call(
    policy: Policy,
    log: AuditLog,
    payload: Any,
    max_calls: int | None = None,
) -> tuple[int, dict[str, Any]]:
    """The decision path, separated from HTTP so a test needs no socket.

    `max_calls` is enforced here and not in the caller: a budget checked between calls
    is a report, and a command can make several calls in the time a poll takes. This is
    the only place every call passes synchronously.
    """
    if not isinstance(payload, dict):
        return 400, {"error": "body must be a JSON object with tool and resource"}
    tool = payload.get("tool")
    resource = payload.get("resource")
    if not isinstance(tool, str) or not isinstance(resource, str) or not tool or not resource:
        return 400, {"error": "tool and resource are required strings"}
    if max_calls is not None and log.calls() >= max_calls:
        decision = Decision(DENY, "budget", f"budget exhausted after {max_calls} call(s)")
        event = log.record(tool, resource, decision)
        return 429, {"decision": decision.as_json(), "event": event}
    decision = policy.decide(tool, resource)
    event = log.record(tool, resource, decision)
    return (200 if decision.allowed else 403), {"decision": decision.as_json(), "event": event}


def serve(
    policy: Policy,
    log: AuditLog,
    host: str = "127.0.0.1",
    port: int = 8765,
    max_calls: int | None = None,
) -> ThreadingHTTPServer:
    """Bind the proxy. `port=0` chooses a free port, which is how tests use it."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 - the stdlib names it
            if self.path != "/health":
                self._send(404, {"error": f"no route {self.path}"})
                return
            self._send(200, {"default": policy.default, "rules": len(policy.rules)})

        def do_POST(self) -> None:  # noqa: N802 - the stdlib names it
            if self.path != "/call":
                self._send(404, {"error": f"no route {self.path}"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw or b"{}")
            except json.JSONDecodeError as exc:
                self._send(400, {"error": f"invalid JSON: {exc}"})
                return
            status, body = handle_call(policy, log, payload, max_calls)
            self._send(status, body)

        def _send(self, status: int, body: dict[str, Any]) -> None:
            data = json.dumps(body, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt: str, *args: Any) -> None:
            # The audit log is the record; the default stderr chatter is noise a
            # replay cannot read.
            return

    return ThreadingHTTPServer((host, port), Handler)
