# SPDX-License-Identifier: Apache-2.0
"""Gates that re-execute on submitted artifacts (issue #15, the visible set behind `V`).

A gate here is a program, not a sentence: it reads the artifact directory an arm
submitted, runs the pinned toolchain on it, and returns pass or fail with the evidence
that decided it. Two rules come from `bendeda/plugins/interfaces.py` and are load-bearing:

- a missing capability is `skip`, never `fail` — an absent simulator is not a defect in
  the design under test;
- a skip is never recorded as a pass, so `score` reports the run as incomplete.

`trace` compiles the submitted `model.bend`, runs it against the submitted `dut.sv` in the
pinned simulator, and passes only when every cycle agrees. `formal` runs every `*.sby`
job in the submission and passes only on the PASS marker. The hidden oracle pack is a
different thing and is scored on the scoring host (§5.4).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from bendeda.conformance.vector_path import (
    DEFAULT_IMAGE,
    compile_model,
    compare,
    default_plan,
    find_bend_toolchain,
    image_available,
    load_plan,
    run_vectors,
    simulate_verilator,
    validate_spec,
)
from bendeda.plugins import GateResult
from bendeda.runner import _docker_path, _run as docker_run

REQUIRED = ("model.bend", "dut.sv", "dut.json")


def _tail(text: str, limit: int = 400) -> str:
    lines = [line for line in (text or "").strip().splitlines() if line.strip()]
    return lines[-1][:limit] if lines else "(no output)"


def _result(
    gate: str, status: str, *, started: float, reason: str | None = None,
    detail: Mapping[str, Any] | None = None,
) -> GateResult:
    return GateResult(
        gate=gate,
        status=status,
        reason=reason,
        detail=dict(detail or {}),
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )


def trace_gate(
    artifacts: str | Path,
    cfg: Mapping[str, Any] | None = None,
    *,
    toolchain=find_bend_toolchain,
    compile_fn=compile_model,
    vectors=run_vectors,
    simulate=simulate_verilator,
    available=image_available,
) -> GateResult:
    """The model/DUT trace gate: agreement is the verdict, a mismatch is a failure."""
    cfg = dict(cfg or {})
    root = Path(artifacts)
    started = time.monotonic()
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        return _result(
            "trace", "fail", started=started,
            reason=f"the submission is missing {', '.join(missing)}",
        )

    bun, cli = toolchain()
    if not bun or not cli:
        return _result(
            "trace", "skip", started=started,
            reason="no pinned Bend compiler (set BENDEDA_BUN and BENDEDA_BEND_CLI)",
        )
    image = str(cfg.get("image") or DEFAULT_IMAGE)
    if not available(image, str(cfg.get("docker", "docker"))):
        return _result(
            "trace", "skip", started=started,
            reason=f"simulator image {image} is not present",
        )
    try:
        plan = (
            load_plan(root / "plan.json")
            if (root / "plan.json").is_file()
            else default_plan(int(cfg.get("cycles", 8)))
        )
        manifest = validate_spec(root / "dut.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _result("trace", "fail", started=started, reason=f"unusable plan or manifest: {exc}")

    # A plan written against the model names `incs`; the generated testbench wants one
    # sequence per input port. For a single-input design those are the same sequence,
    # and saying so is what lets a fixture's own plan reach the simulator.
    inputs = [item["port"] for item in manifest["inputs"]]
    # `load_plan` normalises a missing section to `{}`, so an empty mapping is the
    # "not defined" case — checking only for a non-dict silently kept it empty.
    if not plan.get("stimulus") and len(inputs) == 1:
        plan = {**plan, "stimulus": {inputs[0]: list(plan.get("incs", []))}}

    with tempfile.TemporaryDirectory(prefix="bendeda-gate-trace-") as raw:
        build = Path(raw)
        compiled = compile_fn(root / "model.bend", build / "model.mjs", Path(cli), bun)
        if not compiled.ok:
            return _result(
                "trace", "fail", started=started,
                reason=f"the model does not compile: {_tail(compiled.stderr or compiled.stdout)}",
            )
        try:
            payload = vectors(compiled.output, plan)
        except (OSError, RuntimeError, json.JSONDecodeError) as exc:
            return _result(
                "trace", "skip", started=started,
                reason=f"the vector driver did not run: {exc}",
            )
        try:
            dut_trace = simulate(
                root / "dut.sv",
                manifest,
                plan,
                image=image,
                docker=str(cfg.get("docker", "docker")),
            )
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            return _result(
                "trace", "fail", started=started,
                reason=f"the DUT did not simulate: {exc}",
            )

    comparison = compare(
        payload["steps"], count0=int(plan.get("count0", 0)), dut_trace=dut_trace
    )
    if comparison.mismatches:
        return _result(
            "trace", "fail", started=started,
            reason=f"model and DUT disagree at cycle {comparison.mismatches[0]}",
            detail={
                "cycles": comparison.total,
                "mismatches": list(comparison.mismatches[:8]),
            },
        )
    return _result(
        "trace", "pass", started=started, detail={"cycles": comparison.total}
    )


def formal_gate(
    artifacts: str | Path,
    cfg: Mapping[str, Any] | None = None,
    *,
    run=None,
    available=image_available,
) -> GateResult:
    """Run every `.sby` job in the submission; PASS is a file, not a phrase."""
    cfg = dict(cfg or {})
    root = Path(artifacts)
    started = time.monotonic()
    jobs = sorted(root.glob("*.sby"))
    if not jobs:
        return _result(
            "formal", "fail", started=started,
            reason="the submission has no .sby job, so nothing was proved",
        )
    image = str(cfg.get("image") or DEFAULT_IMAGE)
    if not available(image, str(cfg.get("docker", "docker"))):
        return _result(
            "formal", "skip", started=started,
            reason=f"simulator image {image} is not present",
        )
    run = run or docker_run
    with tempfile.TemporaryDirectory(prefix="bendeda-gate-formal-") as raw:
        work = Path(raw)
        # A copy, because sby writes its own directory and a gate must not mutate the
        # artifacts it judges.
        for item in root.iterdir():
            if item.is_file():
                shutil.copyfile(item, work / item.name)
        for job in jobs:
            out_dir = f"{job.name}.out"
            argv = [
                str(cfg.get("docker", "docker")), "run", "--rm",
                "--mount", f"type=bind,source={_docker_path(work)},target=/work",
                "-w", "/work", image,
                "sby", "-f", job.name, "-d", out_dir,
            ]
            code, output = run(argv)
            if code != 0:
                return _result(
                    "formal", "fail", started=started,
                    reason=f"{job.name} exited {code}: {_tail(output)}",
                )
            if not (work / out_dir / "PASS").exists():
                return _result(
                    "formal", "fail", started=started,
                    reason=f"{job.name} finished without a PASS marker",
                )
    return _result(
        "formal", "pass", started=started,
        detail={"jobs": [job.name for job in jobs]},
    )


GATES = {"trace": trace_gate, "formal": formal_gate}

#: Named gates the design lists but that need something an artifact directory does not
#: carry. Reporting them as planned is what keeps `gate run lint` from looking green.
PLANNED = {
    "lint": "the lint gate needs a task's law package, not an artifact directory (Phase 1.7)",
    "conformance": "the conformance gate arrives with the L2/L3 rungs (Phase 2)",
}


def run_gates(
    artifacts: str | Path,
    names: Sequence[str],
    cfg: Mapping[str, Any] | None = None,
) -> dict[str, GateResult]:
    """Run the named gates. An unknown name raises: silently skipping one is a hole."""
    results: dict[str, GateResult] = {}
    for name in names:
        fn = GATES.get(str(name))
        if fn is None:
            raise KeyError(name)
        results[str(name)] = fn(artifacts, cfg)
    return results


def verdicts(results: Mapping[str, GateResult]) -> dict[str, bool]:
    """The map `score` reads: pass/fail only, so a skip cannot masquerade as a pass."""
    return {
        name: result.status == "pass"
        for name, result in results.items()
        if result.status in ("pass", "fail")
    }


def skipped(results: Mapping[str, GateResult]) -> list[str]:
    return sorted(name for name, result in results.items() if result.status == "skip")


# ---------------------------------------------------------------------------------
# Calibration (GS/GSp, LA4): does the visible gate set reject bugs and accept correct
# implementations? Run over a corpus rather than asserted in prose.
# ---------------------------------------------------------------------------------

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_NOTHING_MEASURED = 3

CORPUS_NAME = "corpus.json"

#: `correct` is an implementation the task accepts; `mutant` and `seeded` are two
#: failure classes the metric reports apart, so a gate cannot look good by catching
#: only the easy half.
KINDS = ("correct", "mutant", "seeded")
BUG_KINDS = ("mutant", "seeded")


@dataclass(frozen=True)
class CorpusEntry:
    id: str
    kind: str
    artifacts: Path
    note: str = ""


@dataclass(frozen=True)
class Corpus:
    """A reference submission plus variants of it.

    An entry replaces the base's files, so a bug is a diff of one file against a
    submission that already passes, and every variant is judged with the same reference
    model, manifest and plan.
    """

    root: Path
    task: str
    base: Path
    gates: tuple[str, ...]
    entries: tuple[CorpusEntry, ...]


def load_corpus(root: str | Path) -> Corpus:
    """Read `corpus.json`, refusing anything a calibration could silently misread."""
    root = Path(root)
    manifest_path = root / CORPUS_NAME
    if not manifest_path.is_file():
        raise ValueError(
            f"no {CORPUS_NAME} in {root}: a corpus is a manifest plus its variants"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{manifest_path}: not JSON ({exc})") from exc
    if not isinstance(manifest, dict):
        raise ValueError(f"{manifest_path}: the manifest must be an object")

    task = str(manifest.get("task") or root.name)
    base = (root / str(manifest.get("base") or ".")).resolve()
    if not base.is_dir():
        raise ValueError(f"{manifest_path}: base {base} is not a directory")

    gates = tuple(str(name) for name in manifest.get("gates") or ())
    unknown = [name for name in gates if name not in GATES]
    if unknown:
        raise ValueError(
            f"{manifest_path}: unknown gate(s) {', '.join(unknown)}; "
            f"implemented: {', '.join(sorted(GATES))}"
        )

    raw = manifest.get("entries")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{manifest_path}: 'entries' must be a non-empty list")
    entries: list[CorpusEntry] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{manifest_path}: entry {index} is not an object")
        identifier = str(item.get("id") or "").strip()
        if not identifier:
            raise ValueError(f"{manifest_path}: entry {index} has no id")
        if identifier in seen:
            raise ValueError(f"{manifest_path}: the id {identifier!r} is used twice")
        seen.add(identifier)
        kind = str(item.get("kind") or "")
        if kind not in KINDS:
            raise ValueError(
                f"{manifest_path}: entry {identifier} has kind {kind!r}; "
                f"expected one of {', '.join(KINDS)}"
            )
        artifacts = (root / str(item.get("artifacts") or identifier)).resolve()
        if not artifacts.is_dir():
            raise ValueError(
                f"{manifest_path}: entry {identifier} has no directory at {artifacts}"
            )
        entries.append(
            CorpusEntry(identifier, kind, artifacts, str(item.get("note") or ""))
        )

    kinds = {entry.kind for entry in entries}
    for needed in KINDS:
        if needed not in kinds:
            raise ValueError(
                f"{manifest_path}: no {needed} entry, so that rate could not be computed"
            )
    return Corpus(root, task, base, gates or tuple(sorted(GATES)), tuple(entries))


def stage(corpus: Corpus, entry: CorpusEntry, target: str | Path) -> None:
    """Copy the base submission, then the entry's overrides over it."""
    target = Path(target)
    for source in (corpus.base, entry.artifacts):
        for item in sorted(source.iterdir()):
            if item.is_file():
                shutil.copyfile(item, target / item.name)


@dataclass(frozen=True)
class CalibrationEntry:
    id: str
    kind: str
    #: `rejected` (a gate failed), `accepted` (every gate passed), or `undecidable`
    #: (a gate could not run, so the entry is neither a catch nor a false assurance).
    verdict: str
    gates: dict[str, str] = field(default_factory=dict)
    reason: str | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "verdict": self.verdict,
            "gates": dict(self.gates),
            "reason": self.reason,
        }


@dataclass
class Calibration:
    task: str
    gates: tuple[str, ...]
    entries: list[CalibrationEntry]

    def _of(self, kinds: Sequence[str]) -> list[CalibrationEntry]:
        return [entry for entry in self.entries if entry.kind in kinds]

    @staticmethod
    def _decided(entries: Sequence[CalibrationEntry]) -> list[CalibrationEntry]:
        return [entry for entry in entries if entry.verdict != "undecidable"]

    def gs(self, kind: str | None = None) -> float | None:
        """Gate Sensitivity: the share of bugs some gate rejected.

        Undecidable entries are excluded from the denominator and reported separately:
        counting a gate that could not run as a miss would blame the gate for the
        machine, and counting it as a catch would invent a result.
        """
        decided = self._decided(self._of((kind,) if kind else BUG_KINDS))
        if not decided:
            return None
        rejected = sum(1 for entry in decided if entry.verdict == "rejected")
        return round(rejected / len(decided), 4)

    def gsp(self) -> float | None:
        """Gate Specificity: the share of correct implementations the gates accepted."""
        decided = self._decided(self._of(("correct",)))
        if not decided:
            return None
        accepted = sum(1 for entry in decided if entry.verdict == "accepted")
        return round(accepted / len(decided), 4)

    def counts(self, kind: str) -> dict[str, int]:
        of_kind = self._of((kind,))
        return {"decided": len(self._decided(of_kind)), "total": len(of_kind)}

    def undecidable(self) -> list[CalibrationEntry]:
        return [entry for entry in self.entries if entry.verdict == "undecidable"]

    def survivors(self) -> list[CalibrationEntry]:
        return [
            entry
            for entry in self._decided(self._of(BUG_KINDS))
            if entry.verdict == "accepted"
        ]

    def false_rejects(self) -> list[CalibrationEntry]:
        return [
            entry
            for entry in self._decided(self._of(("correct",)))
            if entry.verdict == "rejected"
        ]

    def exit_code(self, min_gs: float = 0.95, min_correct: int = 3) -> int:
        """0 calibrated, 1 calibrated and failing, 3 not calibrated at all."""
        correct = self._decided(self._of(("correct",)))
        # LA4 asks for at least three structurally different correct implementations:
        # fewer cannot expose a gate that is fitted to one micro-architecture.
        if self.undecidable() or len(correct) < min_correct:
            return EXIT_NOTHING_MEASURED
        if self.gs() is None or self.gsp() is None:
            return EXIT_NOTHING_MEASURED
        if self.false_rejects() or (self.gs() or 0.0) < min_gs:
            return EXIT_FAIL
        return EXIT_OK

    def as_json(self, min_gs: float = 0.95, min_correct: int = 3) -> dict[str, Any]:
        return {
            "task": self.task,
            "gates": list(self.gates),
            "entries": [entry.as_json() for entry in self.entries],
            "gs": {
                "mutant": self.gs("mutant"),
                "seeded": self.gs("seeded"),
                "overall": self.gs(),
            },
            "gsp": self.gsp(),
            "counts": {kind: self.counts(kind) for kind in KINDS},
            "undecidable": [entry.id for entry in self.undecidable()],
            "survivors": [entry.id for entry in self.survivors()],
            "false_rejects": [entry.id for entry in self.false_rejects()],
            "min_gs": min_gs,
            "min_correct": min_correct,
            "ok": self.exit_code(min_gs, min_correct) == EXIT_OK,
        }


def calibrate(
    corpus: Corpus,
    cfg: Mapping[str, Any] | None = None,
    *,
    gates: Sequence[str] | None = None,
    run=None,
) -> Calibration:
    """Run the gate set on every corpus entry, one staged submission at a time."""
    run = run or run_gates
    names = tuple(gates or corpus.gates)
    calibration = Calibration(corpus.task, names, [])
    for entry in corpus.entries:
        with tempfile.TemporaryDirectory(prefix=f"bendeda-calibrate-{entry.id}-") as raw:
            target = Path(raw)
            stage(corpus, entry, target)
            results = run(target, names, dict(cfg or {}))
        statuses = {name: result.status for name, result in results.items()}
        if "fail" in statuses.values():
            reason = next(
                (
                    results[name].reason
                    for name, status in statuses.items()
                    if status == "fail" and results[name].reason
                ),
                None,
            )
            verdict = "rejected"
        elif "skip" in statuses.values():
            # The gate that could not run cannot be credited with a catch, and it must
            # not accept either: the entry is undecidable until it runs.
            verdict = "undecidable"
            reason = "; ".join(
                f"{name}: {results[name].reason}"
                for name, status in statuses.items()
                if status == "skip"
            )
        elif statuses and all(status == "pass" for status in statuses.values()):
            verdict = "accepted"
            reason = None
        else:
            verdict = "undecidable"
            reason = "no gate reported a verdict"
        calibration.entries.append(
            CalibrationEntry(entry.id, entry.kind, verdict, statuses, reason)
        )
    return calibration
