# SPDX-License-Identifier: Apache-2.0
"""The model half of translation fidelity (TF), step 2 of the design.

TF compares two verdicts on the same stimulus: the law on the Bend model, and the
translated SVA on the RTL. This module computes the first one. It is not `tf run`
(step 4 joins the two sides) and it reports no TF number, because a number
computed from one side would be agreement with itself.

Why a generated module rather than a checker invocation per trace: every B1 law is
closed, so a trace binds every free variable and the law becomes a ground
equation. `bend` proves the symbolic law once (LA1); evaluating a bound instance
per trace is a different operation, and 10,000 checker runs per law would report
per-trace *proof* where there is per-trace *evaluation*. The compiled module is the
evaluator the L1 vector path already uses, so `tf` shares a compiler with the
contract's proof rather than with its own definition.

The generation is a rewrite of each law's claim, not a second statement of the
law. `MkFifo{a, b, level}` — the state the law quantifies over — becomes the
trace's pre-state, the binder `d` becomes the trace's `din`, and the head and
second element binders become the model's own field projections. The equality is
then specialised by the claim's type, because Bend has no polymorphic `==` in a
`def`: `U32.is_eq`, `Nat.is_eq`, and for a `Bool` claim either the expression
itself (it says `== True{}`) or `Bool.not(Bool.xor(l, r))`.

A law this rewrite cannot read is a problem in the report, never a silently
dropped row: "19 rows" is a claim about the plan, and a translator that skips what
it cannot understand makes that claim false.
"""

from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from bendeda.conformance.vector_path import compile_model, find_bend_toolchain
from bendeda.laws.manifest import Manifest
from bendeda.laws.source import BendFile, parse as parse_bend

EXIT_OK = 0
EXIT_DISAGREEMENT = 1
EXIT_NOTHING_MEASURED = 3

DRIVER = Path(__file__).resolve().parents[1] / "tools" / "law_eval.mjs"

KIND_STATE = "state"
KIND_DIN = "din"

#: `count` decodes the level, so the plan's `level` names map onto these values.
LEVEL_BY_COUNT = {0: "Empty", 1: "Half", 2: "Full"}

#: The plan's `observe` names the signal the law's right-hand side constrains. The
#: mapping is used to check the plan against the claim: a plan that says `dout` for
#: a law that never calls `dout` is describing a different law.
OBSERVE_CALLS = {"dout": "dout(", "count": "count(", "full": "is_full(", "empty": "is_empty("}

_STATE = "\x00"
_DIN = "\x01"
_IDENTIFIER = re.compile(r"^[A-Za-z_][\w]*$")


@dataclass(frozen=True)
class Judge:
    """One law, as a generated function of the pre-state (and the input)."""

    fn: str
    law: str
    id: str
    sva: str
    expression: str
    signature: str
    params: tuple[str, ...]
    op: str | None
    plan: Mapping[str, Any]

    @property
    def din_uses(self) -> int:
        return sum(1 for kind in self.params if kind == KIND_DIN)


@dataclass
class Row:
    id: str
    sva: str
    exercised: int = 0
    agreed: int = 0
    disagreed: int = 0
    first_disagreement: dict[str, Any] | None = None
    note: str | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sva": self.sva,
            "exercised": self.exercised,
            "agreed": self.agreed,
            "disagreed": self.disagreed,
            "first_disagreement": self.first_disagreement,
            "note": self.note,
        }


@dataclass
class Report:
    task: str
    traces: int
    cycles: int
    seed: int
    rows: list[Row] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)

    def exit_code(self) -> int:
        """0 every law was exercised and agreed, 1 a finding, 3 nothing measured."""
        if self.problems:
            return EXIT_NOTHING_MEASURED
        if not self.rows:
            return EXIT_NOTHING_MEASURED
        if any(row.exercised == 0 for row in self.rows):
            return EXIT_DISAGREEMENT
        if any(row.disagreed for row in self.rows):
            return EXIT_DISAGREEMENT
        return EXIT_OK

    def as_json(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "side": "model",
            "traces": self.traces,
            "cycles": self.cycles,
            "seed": self.seed,
            "tf": None,
            "tf_note": "TF needs the SVA verdict on the same trace; this run evaluated "
                       "the model side only",
            "laws": [row.as_json() for row in self.rows],
            "problems": list(self.problems),
            "environment": dict(self.environment),
            "ok": self.exit_code() == EXIT_OK,
            "exit": self.exit_code(),
        }


def _state_shape(model_text: str, claim: str) -> tuple[str, str, tuple[str, ...]]:
    """The state type name, its constructor, and the constructor's fields.

    The constructor is read from the law's claim rather than from the model's first
    `type` block: the model also declares `Level` and `Op`, and picking by position
    would take whichever happens to be written first.
    """
    match = re.search(r"\b([A-Z]\w*)\{", claim)
    if match is None:
        raise ValueError("the claim constructs no state, so there is nothing to bind")
    ctor = match.group(1)
    declaration = re.search(rf"^\s+{re.escape(ctor)}\s*\{{([^}}]*)\}}", model_text, re.MULTILINE)
    if declaration is None:
        raise ValueError(f"the model does not declare a `{ctor}` constructor")
    fields = tuple(
        field_name.split(":")[0].strip()
        for field_name in declaration.group(1).split(",")
        if field_name.strip()
    )
    if len(fields) < 2:
        raise ValueError(
            f"`{ctor}` has {len(fields)} field(s); a witness needs a head and a second element"
        )
    head = re.search(
        rf"^type\s+(\w+)\s+is\s+\w+\s*:\s*\n\s+{re.escape(ctor)}\s*\{{", model_text, re.MULTILINE
    )
    if head is None:
        raise ValueError(f"`{ctor}` is not declared inside a `type` block of the model")
    return head.group(1), ctor, fields


def _split_equality(claim: str) -> tuple[str, str] | None:
    """Split at the single `==` that sits outside every bracket (rule L013)."""
    depth = 0
    for index, char in enumerate(claim):
        if char in "({[":
            depth += 1
        elif char in ")}]":
            depth -= 1
        elif depth == 0 and claim[index : index + 2] == "==":
            return claim[:index].strip(), claim[index + 2 :].strip()
    return None


def _replace_state(text: str, ctor_pattern: str, fields: Sequence[str]) -> str:
    """Substitute the law's quantified state and its field binders."""
    text = re.sub(ctor_pattern, _STATE, text)
    text = re.sub(rf"\b{re.escape(fields[0])}\b", f"tf_head({_STATE})", text)
    text = re.sub(rf"\b{re.escape(fields[1])}\b", f"tf_second({_STATE})", text)
    return re.sub(r"\bd\b", _DIN, text)


def _bind(
    expression: str, state_type: str
) -> tuple[str, str, tuple[str, ...]]:
    """Give every placeholder its own parameter.

    Bend bindings are affine, so a law that mentions the pre-state twice needs two
    parameters. The driver passes the same value to each; making the duplication
    explicit is weaker than `dup` and stronger than silently sharing a binding the
    compiler would reject.
    """
    params: list[str] = []
    kinds: list[str] = []
    counter = {"s": 0, "din": 0}

    def substitute(match: re.Match[str]) -> str:
        base = "s" if match.group(0) == _STATE else "din"
        name = f"{base}{counter[base]}"
        counter[base] += 1
        params.append(f"{name}: {state_type if base == 's' else 'U32'}")
        kinds.append(KIND_STATE if base == "s" else KIND_DIN)
        return name

    rendered = re.sub(f"[{_STATE}{_DIN}]", substitute, expression)
    return rendered, ", ".join(params), tuple(kinds)


def _law_op(claim: str, ctor_pattern: str) -> str | None:
    match = re.search(rf"step\(\s*{ctor_pattern}\s*,\s*(\w+)\s*\{{", claim)
    return match.group(1) if match else None


def _check_plan(plan: Any, claim: str, fields: Sequence[str]) -> list[str]:
    """The plan's consistency with the claim it claims to describe."""
    if not isinstance(plan, Mapping):
        return [f"fidelity_plan is {type(plan).__name__}, expected a mapping"]
    problems: list[str] = []
    window = plan.get("window")
    if window != 1:
        problems.append(
            f"fidelity_plan.window is {window!r}; only 1 is supported, because a windowed "
            "judge needs a trace-indexed law the model cannot yet state (BendBV #8)"
        )
    for name in plan.get("observe") or ():
        call = OBSERVE_CALLS.get(str(name))
        if call is None:
            problems.append(f"fidelity_plan.observe names {name!r}, which is not a known signal")
        elif call not in claim:
            problems.append(
                f"fidelity_plan.observe names {name!r} but the claim never calls `{call[:-1]}`"
            )
    distinct = plan.get("distinct") or ()
    if not isinstance(distinct, (list, tuple)):
        problems.append("fidelity_plan.distinct must be a list")
    else:
        unknown = [binder for binder in distinct if binder not in fields]
        if unknown:
            problems.append(
                f"fidelity_plan.distinct names {unknown}, but the law binds {list(fields)}"
            )
    return problems


def build_judges(
    model_text: str, manifest: Manifest, laws: BendFile
) -> tuple[list[Judge], list[str]]:
    """One judge per translated law, plus the reason for every law that has none."""
    translated = [e for e in manifest.laws if e.translation and e.translation.get("sva")]
    if not translated:
        return [], ["no law in the manifest declares a translation, so there is nothing to judge"]
    first_claim = laws.law(translated[0].name)
    if first_claim is None:
        return [], [f"the manifest translates `{translated[0].name}`, which LAWS.bend does not state"]
    try:
        state_type, ctor, fields = _state_shape(model_text, first_claim.claim)
    except ValueError as exc:
        return [], [f"cannot read the state the laws quantify over: {exc}"]

    ctor_pattern = re.escape(ctor) + r"\{(?:[^{}]*(?:\{[^}]*\})?[^{}]*)\}"
    judges: list[Judge] = []
    problems: list[str] = []
    for entry in translated:
        law = laws.law(entry.name)
        if law is None:
            problems.append(f"{entry.name}: the manifest translates it but LAWS.bend does not state it")
            continue
        plan = entry.translation.get("fidelity_plan")
        if plan is None:
            problems.append(f"{entry.name}: the translation declares no fidelity_plan")
            continue
        plan_problems = _check_plan(plan, law.claim, fields)
        if plan_problems:
            problems.extend(f"{entry.name}: {problem}" for problem in plan_problems)
            continue
        parts = _split_equality(law.claim)
        if parts is None:
            problems.append(f"{entry.name}: the claim has no top-level `==` to turn into a judge")
            continue
        left = _replace_state(parts[0], ctor_pattern, fields)
        right = _replace_state(parts[1], ctor_pattern, fields)
        if law.claim_type == "Bool":
            if right == "True{}":
                body = left
            elif right == "False{}":
                body = f"Bool.not({left})"
            else:
                body = f"Bool.not(Bool.xor({left}, {right}))"
        elif law.claim_type == "U32":
            body = f"U32.is_eq({left}, {right})"
        elif law.claim_type == "Nat":
            body = f"Nat.is_eq({left}, {right})"
        else:
            problems.append(
                f"{entry.name}: no equality for a {law.claim_type!r} claim; the generator "
                "knows Bool, U32 and Nat"
            )
            continue
        expression, signature, params = _bind(body, state_type)
        op = _law_op(law.claim, ctor_pattern)
        declared = plan.get("ops") or ()
        if op is not None and declared and op not in declared:
            problems.append(
                f"{entry.name}: the law steps with `{op}` but the plan lists {list(declared)}; "
                "the stimulus it asks for would never exercise the law"
            )
            continue
        judges.append(
            Judge(
                fn=f"tf_{entry.name}",
                law=entry.name,
                id=entry.id,
                sva=str(entry.translation.get("sva")),
                expression=expression,
                signature=signature,
                params=params,
                op=op,
                plan=dict(plan),
            )
        )
    return judges, problems


def render_judge_module(model_text: str, judges: Sequence[Judge], ctor: str, fields: Sequence[str], state_type: str) -> str:
    """The `.bend` source: the model inlined, then one function per judge."""
    body = re.sub(r"^import Base\s*$", "", model_text, flags=re.MULTILINE).strip("\n")
    lines = [
        "# SPDX-License-Identifier: Apache-2.0",
        "# Generated by bendeda.tf: the model, the field projections, and one judge",
        "# per translated law. Do not edit; regenerate from model.bend and LAWS.bend.",
        "",
        "import Base",
        body,
        "",
        f"def tf_head(s: {state_type}) -> U32:",
        "  match s:",
        f"    case {ctor}{{{', '.join(fields)}}}:",
        f"      {fields[0]}",
        "",
        f"def tf_second(s: {state_type}) -> U32:",
        "  match s:",
        f"    case {ctor}{{{', '.join(fields)}}}:",
        f"      {fields[1]}",
        "",
    ]
    for judge in judges:
        lines += [f"def {judge.fn}({judge.signature}) -> Bool:", f"  {judge.expression}", ""]
    return "\n".join(lines)


def make_traces(count: int, cycles: int, seed: int) -> list[dict[str, Any]]:
    """Deterministic random stimulus: a seeded op stream per trace.

    Shared by both sides of TF later, so it is generated here and recorded in the
    report: a disagreement that cannot be replayed is not evidence.
    """
    rng = random.Random(seed)
    choices = (("Push", True), ("Pop", False), ("PushPop", True), ("Idle", False))
    traces: list[dict[str, Any]] = []
    for _ in range(count):
        ops = []
        for _ in range(cycles):
            op, has_din = rng.choice(choices)
            ops.append({"op": op, "din": rng.randrange(1 << 32) if has_din else None})
        traces.append({"ops": ops})
    return traces


def _gated(judge: Judge, cycle: Mapping[str, Any]) -> str | None:
    """Why this cycle does not exercise the law, or None when it does."""
    level = judge.plan.get("level")
    if level and level != "any":
        actual = LEVEL_BY_COUNT.get(cycle.get("count"))
        if actual != level:
            return f"level {actual} is not {level}"
    if judge.op is not None and cycle.get("op") != judge.op:
        return f"the cycle's operation is {cycle.get('op')}, not {judge.op}"
    distinct = judge.plan.get("distinct") or ()
    if len(distinct) >= 2 and cycle.get("head") == cycle.get("second"):
        return f"the state's elements coincide ({cycle.get('head')!r})"
    return None


def _aggregate(judges: Sequence[Judge], traces: Sequence[Sequence[Mapping[str, Any]]]) -> list[Row]:
    rows = [
        Row(judge.id, judge.sva, note=None)
        for judge in judges
    ]
    for row, judge in zip(rows, judges):
        for trace_index, cycles in enumerate(traces):
            for cycle in cycles:
                if _gated(judge, cycle) is not None:
                    continue
                row.exercised += 1
                verdict = (cycle.get("verdicts") or {}).get(judge.fn)
                if verdict is True:
                    row.agreed += 1
                elif verdict is False:
                    row.disagreed += 1
                else:
                    # A judge that threw is an evaluator failure, not a law that
                    # failed: it is counted as a disagreement with the reason kept.
                    row.disagreed += 1
                    if row.first_disagreement is None:
                        row.first_disagreement = {
                            "trace": trace_index,
                            "cycle": cycle.get("cycle"),
                            "reason": (verdict or {}).get("error") if isinstance(verdict, dict) else "no verdict",
                        }
                    continue
                if verdict is False and row.first_disagreement is None:
                    row.first_disagreement = {
                        "trace": trace_index,
                        "cycle": cycle.get("cycle"),
                        "binders": {"din": cycle.get("din"), "head": cycle.get("head"), "second": cycle.get("second")},
                    }
        if row.exercised == 0:
            row.note = (
                f"the plan's stimulus never reached {judge.plan.get('level')} with "
                f"{judge.op or 'any operation'}"
            )
    return rows


def _run_driver(
    module: Path, plan: Mapping[str, Any], driver: Path, node: str, timeout: int
) -> dict[str, Any]:
    plan_path = module.with_suffix(".plan.json")
    plan_path.write_text(json.dumps(plan), encoding="utf-8", newline="")
    try:
        done = subprocess.run(
            [node, str(driver), str(module), str(plan_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"the law driver did not run: {exc}") from exc
    if done.returncode != 0:
        raise RuntimeError(
            f"the law driver exited {done.returncode}: {(done.stderr or done.stdout).strip()[:800]}"
        )
    return json.loads(done.stdout)


def evaluate(
    task: str | Path,
    *,
    traces: int = 1000,
    cycles: int = 8,
    seed: int = 20261128,
    driver: Path = DRIVER,
    node: str | None = None,
    workdir: Path | None = None,
    timeout: int = 600,
) -> Report:
    """Evaluate every translated law on random traces of the reference model."""
    root = Path(task)
    report = Report(task=root.name, traces=traces, cycles=cycles, seed=seed)
    try:
        manifest = Manifest.load(root / "laws.manifest.yaml")
        laws = parse_bend((root / "LAWS.bend").read_text(encoding="utf-8"), root / "LAWS.bend")
        model_text = (root / "model.bend").read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        report.problems.append(f"cannot read the task package: {exc}")
        return report
    report.task = manifest.task

    judges, problems = build_judges(model_text, manifest, laws)
    report.problems.extend(problems)
    state_type, ctor, fields = None, None, None
    if judges:
        try:
            state_type, ctor, fields = _state_shape(model_text, laws.law(judges[0].law).claim)
        except ValueError as exc:
            report.problems.append(f"cannot read the state: {exc}")
            judges = []

    bun, cli = find_bend_toolchain()
    if not bun or not cli:
        report.problems.append(
            "no pinned Bend compiler (set BENDEDA_BUN and BENDEDA_BEND_CLI), so the "
            "model side of TF was not measured"
        )
        report.rows = [Row(judge.id, judge.sva) for judge in judges]
        return report
    node = node or shutil.which("node")
    if not node:
        report.problems.append("no `node` on PATH, so the emitted judge module cannot be executed")
        report.rows = [Row(judge.id, judge.sva) for judge in judges]
        return report

    report.environment = {"bun": str(bun), "bend_cli": str(cli), "node": node}
    if not judges:
        return report

    temporary = tempfile.TemporaryDirectory(prefix="bendeda-tf-") if workdir is None else None
    try:
        build = Path(workdir) if workdir is not None else Path(temporary.name)
        build.mkdir(parents=True, exist_ok=True)
        source = build / "judge.bend"
        source.write_text(
            render_judge_module(model_text, judges, ctor, fields, state_type),
            encoding="utf-8",
            newline="\n",
        )
        compiled = compile_model(source, build / "judge.mjs", Path(cli), str(bun))
        if not compiled.ok:
            report.problems.append(
                f"the judge module does not compile: "
                f"{(compiled.stderr or compiled.stdout).strip()[:800]}"
            )
            report.rows = [Row(judge.id, judge.sva) for judge in judges]
            return report
        plan = {
            "traces": make_traces(traces, cycles, seed),
            "judges": [{"fn": judge.fn, "params": list(judge.params)} for judge in judges],
        }
        try:
            payload = _run_driver(compiled.output, plan, driver, node, timeout)
        except (RuntimeError, json.JSONDecodeError) as exc:
            report.problems.append(str(exc))
            report.rows = [Row(judge.id, judge.sva) for judge in judges]
            return report
        report.rows = _aggregate(judges, payload.get("traces") or [])
        report.environment["runtime"] = str(payload.get("runtime", ""))
        if len(payload.get("traces") or []) != traces:
            report.problems.append(
                f"the driver returned {len(payload.get('traces') or [])} traces for {traces} asked"
            )
    finally:
        if temporary is not None:
            temporary.cleanup()
    return report
