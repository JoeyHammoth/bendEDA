# SPDX-License-Identifier: Apache-2.0
"""Adapter interfaces from §14.2/§14.5.

These are `Protocol`s, so a plugin does not import the harness to be usable and
the harness does not import a plugin to describe it. A future contributor can
ship an adapter in their own package and register it through an entry point.

Every interface carries the same expectation: return structured results, never
raise for an expected failure, and never decide a verdict by language model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class LawVerdict:
    law_id: str
    name: str
    status: str  # proved | failed | missing | unproved | not_run
    elapsed_ms: int | None = None
    checker: str = "default"  # default | verdict | evaluator
    detail: str | None = None


@dataclass(frozen=True)
class CanaryReport:
    false_accepts: int
    false_rejects: int
    controls_run: int
    notes: Sequence[str] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.false_accepts == 0


@dataclass(frozen=True)
class GateResult:
    gate: str
    status: str  # pass | fail | skip | error
    detail: Mapping[str, Any] = field(default_factory=dict)
    elapsed_ms: int | None = None
    reason: str | None = None  # required when status == skip


@dataclass(frozen=True)
class OracleResult:
    oracle_pass: bool
    components: Mapping[str, str]
    failed_requirements: Sequence[str] = field(default_factory=tuple)
    mutants_killed_by_visible: float | None = None
    mutants_killed_by_oracle: float | None = None


class LawLanguage(Protocol):
    name: str
    version: str

    def check(self, laws_path: str, proof_path: str) -> Sequence[LawVerdict]:
        """Per-law verdicts from the real checker, not from reasoning."""

    def evaluate(self, model_path: str, entry: str, args: Mapping[str, Any]) -> Mapping[str, Any]:
        """Execute the reference model (Bend's `-o model.mjs` path)."""

    def canary(self) -> CanaryReport:
        """Negative controls: a false accept blocks every Bend arm."""


class Translator(Protocol):
    def translate(self, law: Mapping[str, Any], abs_map: Mapping[str, Any]) -> Mapping[str, Any]:
        """Produce a property plus the rung of the ladder it lands on."""

    def fidelity_plan(self, law: Mapping[str, Any]) -> Mapping[str, Any]:
        """Declare how translation fidelity for this law will be measured."""


class Gate(Protocol):
    name: str

    def run(self, artifacts: Mapping[str, Any], cfg: Mapping[str, Any]) -> GateResult:
        """Skip, never fail, when a required capability (image, hardware) is absent."""


class Oracle(Protocol):
    def score(self, run_dir: str, pack_dir: str) -> OracleResult:
        """Runs only on the scoring host; never inside the agent container."""


class HardwareBoard(Protocol):
    """Deferred extension (§14.10). Gates that require it must skip when absent."""

    id: str

    def provision(self) -> Mapping[str, Any]: ...
    def program(self, artifact_path: str) -> None: ...
    def run_stimulus(self, vectors_path: str, timeout_s: int) -> Mapping[str, Any]: ...
    def reset(self) -> None: ...
    def attest(self) -> Mapping[str, Any]: ...
