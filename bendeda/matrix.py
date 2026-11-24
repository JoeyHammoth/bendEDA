# SPDX-License-Identifier: Apache-2.0
"""The run matrix: cells, and what executing one cell leaves behind (issue #15).

A matrix is a JSON file listing tasks, arms and seeds. Expanding it is deterministic, so
the run order can be logged and repeated. Executing a cell starts a sandbox, runs the
arm's command inside it, records the submission, tears the sandbox down, re-executes the
visible gates on what the arm left in its workspace, and scores the bundle.

`bendeda run` reports its cells as scored only when `score` says so. The oracle pack is
scored on the scoring host (§5.4), so a cell run here is complete on `S` and `V` and
incomplete on `O` — the matrix says that rather than inventing a verdict.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from bendeda.gates import run_gates, skipped, verdicts
from bendeda.proxy import Policy
from bendeda.runner import AGENT_NAME, AgentSpec, down, exec_in, submit, up
from bendeda.score import load as load_bundle, report

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,60}$")
AGENT = AGENT_NAME


@dataclass(frozen=True)
class Task:
    name: str
    artifacts: Path


@dataclass(frozen=True)
class Cell:
    task: Task
    arm: str
    seed: int

    @property
    def label(self) -> str:
        return f"{self.arm}-{self.task.name}-s{self.seed}"


@dataclass(frozen=True)
class Matrix:
    name: str
    path: Path
    image: str
    sim_image: str
    network: str
    policy: Path | None
    command: tuple[str, ...]
    budgets: Mapping[str, int]
    visible_gates: tuple[str, ...]
    tasks: tuple[Task, ...]
    arms: tuple[str, ...]
    seeds: tuple[int, ...]


def load(path: str | Path) -> Matrix:
    """Read and validate a matrix file. Every rejection names the field."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: expected an object")
    name = str(data.get("name", ""))
    if not NAME.match(name):
        raise ValueError(f"{path.name}: name must match {NAME.pattern}")

    tasks_raw = data.get("tasks")
    if not isinstance(tasks_raw, list) or not tasks_raw:
        raise ValueError(f"{path.name}: tasks must be a non-empty list")
    tasks: list[Task] = []
    for entry in tasks_raw:
        if isinstance(entry, str):
            entry = {"name": entry, "artifacts": f"experiments/fixtures/{entry}"}
        if not isinstance(entry, dict) or "name" not in entry or "artifacts" not in entry:
            raise ValueError(f"{path.name}: each task needs name and artifacts")
        artifacts = Path(str(entry["artifacts"]))
        if not artifacts.is_dir():
            raise ValueError(f"{path.name}: task {entry['name']} has no artifacts at {artifacts}")
        tasks.append(Task(str(entry["name"]), artifacts))

    arms = data.get("arms")
    if not isinstance(arms, list) or not arms:
        raise ValueError(f"{path.name}: arms must be a non-empty list")
    seeds = data.get("seeds", [1])
    if not isinstance(seeds, list) or not seeds or not all(isinstance(s, int) and s >= 1 for s in seeds):
        raise ValueError(f"{path.name}: seeds must be a non-empty list of positive integers")
    command = data.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(c, str) for c in command):
        raise ValueError(f"{path.name}: command must be a non-empty list of strings")
    gates = data.get("visible_gates", ["trace"])
    if not isinstance(gates, list) or not gates:
        raise ValueError(f"{path.name}: visible_gates must be a non-empty list")

    policy = data.get("policy")
    return Matrix(
        name=name,
        path=path,
        image=str(data.get("image", "bendeda/harness:0.0.1")),
        # The agent's image and the simulator's are different things; using one for
        # both made the trace gate report a fail because the harness has no Verilator.
        sim_image=str(data.get("sim_image", "bendeda/oss-cad:2026-11-20")),
        network=str(data.get("network", "bendeda-offline")),
        policy=Path(str(policy)) if policy else None,
        command=tuple(str(c) for c in command),
        budgets=dict(data.get("budgets", {"tool_calls": 400})),
        visible_gates=tuple(str(g) for g in gates),
        tasks=tuple(tasks),
        arms=tuple(str(a) for a in arms),
        seeds=tuple(int(s) for s in seeds),
    )


def expand(matrix: Matrix) -> list[Cell]:
    """Task-major, then arm, then seed: the same order every time for the same file."""
    return [
        Cell(task=task, arm=arm, seed=seed)
        for task in matrix.tasks
        for arm in matrix.arms
        for seed in matrix.seeds
    ]


def _tail(text: str, limit: int = 400) -> str:
    lines = [line for line in (text or "").strip().splitlines() if line.strip()]
    return lines[-1][:limit] if lines else "(no output)"


def default_deps() -> dict[str, Callable[..., Any]]:
    """The real collaborators, named once so tests can substitute them."""

    def gate_results(artifacts: Path, names: Sequence[str], image: str) -> dict[str, Any]:
        return run_gates(artifacts, names, {"image": image})

    def score_bundle(bundle: Path, policy: Path | None):
        return report(load_bundle(bundle), Policy.load(policy) if policy else None)

    return {
        "up": up,
        "exec": exec_in,
        "submit": submit,
        "down": down,
        "gates": gate_results,
        "score": score_bundle,
    }


def execute_cell(
    matrix: Matrix,
    cell: Cell,
    out_root: str | Path,
    deps: Mapping[str, Callable[..., Any]] | None = None,
) -> dict[str, Any]:
    """Run one cell and leave a bundle another machine can score."""
    deps = dict(deps or default_deps())
    bundle = Path(out_root) / matrix.name / cell.label
    bundle.mkdir(parents=True, exist_ok=True)
    events = bundle / "events.jsonl"
    spec = AgentSpec(
        workspace=cell.task.artifacts,
        image=matrix.image,
        network=matrix.network,
        policy=matrix.policy,
        events=events,
    )
    record: dict[str, Any] = {
        "cell": cell.label,
        "task": cell.task.name,
        "arm": cell.arm,
        "seed": cell.seed,
        "artifacts": str(cell.task.artifacts),
        "bundle": str(bundle),
        "error": None,
    }
    try:
        deps["up"](spec)
        code, output = deps["exec"](AGENT, list(matrix.command))
        if code != 0:
            # A crashed arm is a scored zero, not an exclusion: the log simply never
            # records a submission, and `score` turns that into S=0.
            record["error"] = f"the arm's command exited {code}: {_tail(output)}"
        else:
            code, output = deps["submit"](AGENT, f"{cell.task.name}/submission")
            if code != 0:
                # A policy that forbids `submit` cannot produce a submitted run; saying
                # so here is better than letting the log look like a silent zero.
                record["error"] = f"the submission was refused: {_tail(output)}"
    except Exception as exc:  # teardown must happen even when a step blew up
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        deps["down"](spec)

    results = deps["gates"](cell.task.artifacts, list(matrix.visible_gates), matrix.sim_image)
    (bundle / "gates.json").write_text(json.dumps(verdicts(results), indent=2, sort_keys=True), encoding="utf-8")
    (bundle / "expected.json").write_text(
        json.dumps({"visible_gates": list(matrix.visible_gates)}, indent=2), encoding="utf-8"
    )
    skipped_gates = skipped(results)
    if skipped_gates:
        record["skipped"] = skipped_gates
    # A proxy that made no decision left no file; an empty log is a fact about the run
    # (nothing was submitted), not a reason to refuse to score it.
    events.touch(exist_ok=True)

    scored = deps["score"](bundle, matrix.policy)
    (bundle / "score.json").write_text(json.dumps(scored.as_json(), indent=2, sort_keys=True), encoding="utf-8")
    record.update(
        {
            "S": scored.score.S,
            "V": scored.score.V,
            "O": scored.score.O,
            "complete": scored.score.complete,
            "scored": scored.score.scored,
            "report": scored.as_json(),
        }
    )
    (bundle / "cell.json").write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    return record
