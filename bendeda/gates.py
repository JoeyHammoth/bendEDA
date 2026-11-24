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
