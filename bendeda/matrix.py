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

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from bendeda import __version__
from bendeda.gates import run_gates, skipped, verdicts
from bendeda.proxy import Policy
from bendeda.runner import (
    AGENT_NAME,
    AgentSpec,
    _run as docker_run,
    down,
    exec_enforced,
    exec_in,
    submit,
    up,
)
from bendeda.score import load as load_bundle, report

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,60}$")
AGENT = AGENT_NAME
ORDER_METHODS = ("declared", "hash-v1")


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
    order: Mapping[str, Any] | None = None
    prereg: str = ""


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
    image = str(data.get("image", "bendeda/harness:0.0.1"))
    # The agent's image and the simulator's are different things; using one for
    # both made the trace gate report a fail because the harness has no Verilator.
    sim_image = str(data.get("sim_image", "bendeda/oss-cad:2026-11-20"))
    network = str(data.get("network", "bendeda-offline"))
    declared_budgets = dict(data.get("budgets", {"tool_calls": 400}))
    budgets = {str(key): int(value) for key, value in declared_budgets.items()}
    visible_gates = tuple(str(g) for g in gates)
    arm_names = tuple(str(a) for a in arms)
    seed_values = tuple(int(s) for s in seeds)
    order = _order(path, data.get("order"))
    prereg = _prereg(
        name=name,
        image=image,
        sim_image=sim_image,
        network=network,
        policy=str(policy) if policy else None,
        command=[str(c) for c in command],
        budgets=budgets,
        visible_gates=list(visible_gates),
        tasks=[{"name": task.name, "artifacts": task.artifacts.as_posix()} for task in tasks],
        arms=list(arm_names),
        seeds=list(seed_values),
        order=order,
    )
    return Matrix(
        name=name,
        path=path,
        image=image,
        sim_image=sim_image,
        network=network,
        policy=Path(str(policy)) if policy else None,
        command=tuple(str(c) for c in command),
        budgets=budgets,
        visible_gates=visible_gates,
        tasks=tuple(tasks),
        arms=arm_names,
        seeds=seed_values,
        order=order,
        prereg=prereg,
    )


def _order(path: Path, raw: Any) -> dict[str, Any] | None:
    """The ordering declaration, or None for the declared task/arm/seed order."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: order must be an object with method and seed")
    method = str(raw.get("method", "hash-v1"))
    if method not in ORDER_METHODS:
        raise ValueError(f"{path.name}: order.method must be one of {', '.join(ORDER_METHODS)}")
    seed = raw.get("seed", 1)
    if not isinstance(seed, int) or seed < 1:
        raise ValueError(f"{path.name}: order.seed must be a positive integer")
    return {"method": method, "seed": seed}


def _prereg(**declaration: Any) -> str:
    """One hash over everything a run declares, so an edit after freezing shows.

    The hash covers the folded defaults as well as the file's values: changing a
    default in this module changes every prereg, which is the point — a run whose
    meaning moved under it is not the run that was frozen.
    """
    canonical = json.dumps(declaration, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def expand(matrix: Matrix) -> list[Cell]:
    """The declared order, or a seeded hash order that ignores declaration order.

    `hash-v1` sorts each label by `sha256("<seed>:<label>")`. That is stable across
    machines and Python versions — there is no RNG state to reproduce — and it spreads
    arms across the run, so a slow service cannot quietly become an arm effect.
    """
    cells = [
        Cell(task=task, arm=arm, seed=seed)
        for task in matrix.tasks
        for arm in matrix.arms
        for seed in matrix.seeds
    ]
    if matrix.order and matrix.order["method"] == "hash-v1":
        seed = int(matrix.order["seed"])
        cells.sort(
            key=lambda cell: hashlib.sha256(f"{seed}:{cell.label}".encode()).hexdigest()
        )
    return cells


def _tail(text: str, limit: int = 400) -> str:
    lines = [line for line in (text or "").strip().splitlines() if line.strip()]
    return lines[-1][:limit] if lines else "(no output)"


def _bend_release(text: str) -> str | None:
    """The Bend release from versions.lock, without taking a YAML dependency."""
    section = None
    for line in text.splitlines():
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            section = line.rstrip()[:-1]
            continue
        if section == "bend":
            match = re.match(r'\s+release:\s*"([^"]+)"', line)
            if match:
                return match.group(1)
    return None


def environment(
    agent_image: str,
    sim_image: str,
    *,
    versions: Path = Path("docker/versions.lock"),
    inspect=None,
    package_version: str | None = None,
) -> dict[str, Any]:
    """What produced this run, named by digest rather than by tag.

    Issue #6's criterion 2 asks for the compiler version and the image digests in the
    run record. A tag can be rebuilt to point at other bytes; a digest cannot, which is
    why `docker image inspect` is asked rather than the name being copied.
    """
    inspect = inspect or docker_run

    def digest(image: str) -> str | None:
        code, output = inspect(["docker", "image", "inspect", image, "--format", "{{.Id}}"])
        return output.strip() if code == 0 and output.strip() else None

    try:
        lock = Path(versions).read_text(encoding="utf-8")
    except OSError:
        lock = ""
    return {
        "bendeda": package_version or __version__,
        "bend_release": _bend_release(lock),
        "agent_image": {"name": agent_image, "digest": digest(agent_image)},
        "sim_image": {"name": sim_image, "digest": digest(sim_image)},
    }


def default_deps() -> dict[str, Callable[..., Any]]:
    """The real collaborators, named once so tests can substitute them."""

    def run_arm(container: str, argv: Sequence[str], events: Path, budget: Mapping[str, int]):
        calls = int(budget.get("tool_calls") or 0)
        if calls:
            result = exec_enforced(container, argv, events, calls, budget.get("wall_min"))
            return result.code, result.output, result.exhausted
        code, output = exec_in(container, argv)
        return code, output, False

    def gate_results(artifacts: Path, names: Sequence[str], image: str) -> dict[str, Any]:
        return run_gates(artifacts, names, {"image": image})

    def score_bundle(bundle: Path, policy: Path | None):
        return report(load_bundle(bundle), Policy.load(policy) if policy else None)

    return {
        "up": up,
        "exec": run_arm,
        "submit": submit,
        "down": down,
        "gates": gate_results,
        "score": score_bundle,
        "environment": lambda matrix: environment(matrix.image, matrix.sim_image),
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
        max_calls=int(matrix.budgets.get("tool_calls") or 0) or None,
    )
    record: dict[str, Any] = {
        "cell": cell.label,
        "task": cell.task.name,
        "arm": cell.arm,
        "seed": cell.seed,
        "artifacts": str(cell.task.artifacts),
        "bundle": str(bundle),
        "error": None,
        "budget_exhausted": False,
        "prereg": matrix.prereg,
    }
    record["excluded"] = False
    infra: str | None = None
    try:
        deps["up"](spec)
        try:
            code, output, exhausted = deps["exec"](
                AGENT, list(matrix.command), events, dict(matrix.budgets)
            )
        except Exception as exc:
            infra = f"the sandbox failed while the arm ran: {type(exc).__name__}: {exc}"
        else:
            record["budget_exhausted"] = exhausted
            if exhausted:
                # The sandbox was stopped because the allowance ran out: a result, and a
                # scored zero, not an infrastructure failure.
                record["error"] = "the budget was exhausted; the sandbox was stopped"
            elif code != 0:
                # A crashed arm is a scored zero, not an exclusion: the log never records
                # a submission, and `score` turns that into S=0.
                record["error"] = f"the arm's command exited {code}: {_tail(output)}"
            else:
                try:
                    code, output = deps["submit"](AGENT, f"{cell.task.name}/submission")
                except Exception as exc:
                    infra = f"the submission could not be recorded: {type(exc).__name__}: {exc}"
                else:
                    if code != 0:
                        # A policy that forbids `submit` cannot produce a submitted run;
                        # saying so beats letting the log look like a silent zero.
                        record["error"] = f"the submission was refused: {_tail(output)}"
    except Exception as exc:  # `up` failed, so nothing could run at all
        infra = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            deps["down"](spec)
        except Exception as exc:  # teardown failing is infrastructure, not a score
            infra = infra or f"teardown failed: {type(exc).__name__}: {exc}"

    if infra:
        # §11.3: an infrastructure failure voids the run and is re-run, so it is written
        # as such. The first live budget run scored a sandbox that never started as S=0,
        # which is the exact confusion this event exists to prevent.
        events.parent.mkdir(parents=True, exist_ok=True)
        with events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"seq": 0, "tool": "infra", "resource": infra}) + "\n")
        record["error"] = infra
        record["excluded"] = True

    if not record["excluded"]:
        # Gates judge what the arm submitted; after a void run there is nothing to judge.
        results = deps["gates"](
            cell.task.artifacts, list(matrix.visible_gates), matrix.sim_image
        )
        (bundle / "gates.json").write_text(
            json.dumps(verdicts(results), indent=2, sort_keys=True), encoding="utf-8"
        )
        skipped_gates = skipped(results)
        if skipped_gates:
            record["skipped"] = skipped_gates
    (bundle / "expected.json").write_text(
        json.dumps(
            {"visible_gates": list(matrix.visible_gates), "budgets": dict(matrix.budgets)},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    produced_by = deps["environment"](matrix)
    (bundle / "environment.json").write_text(
        json.dumps(produced_by, indent=2, sort_keys=True), encoding="utf-8"
    )
    record["environment"] = produced_by
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
