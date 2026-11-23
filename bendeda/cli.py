# SPDX-License-Identifier: Apache-2.0
"""`bendeda` command line.

Design rule for this package: a command that is not implemented must fail
loudly and say what it will do. A stub that exits 0 would let a person or an
agent believe a gate ran when nothing ran, which is the exact failure mode the
research programme studies.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from bendeda import __version__
from bendeda.conformance import vector_path as conformance

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NOT_IMPLEMENTED = 3
EXIT_CHECK_FAILED = 1

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


def _todo(command: str, plan: str, phase: str) -> int:
    """Report a planned command without pretending it ran."""
    print(f"bendeda {command}: not implemented yet", file=sys.stderr)
    print(f"  planned : {plan}", file=sys.stderr)
    print(f"  lands in: {phase}", file=sys.stderr)
    print("  this command deliberately exits non-zero so nothing can mistake it for a pass.", file=sys.stderr)
    return EXIT_NOT_IMPLEMENTED


def _load_jsonschema_or_none():
    try:
        import jsonschema  # type: ignore

        return jsonschema
    except ImportError:
        return None


def validate_all(quiet: bool = False) -> int:
    """Validate shipped schemas and any task packages that exist."""
    schema_dir = SCHEMA_DIR
    schemas = sorted(schema_dir.glob("*.schema.json")) if schema_dir.exists() else []
    problems: list[str] = []

    for schema_path in schemas:
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{schema_path.name}: invalid JSON ({exc})")
            continue
        if "$schema" not in schema or "title" not in schema:
            problems.append(f"{schema_path.name}: missing $schema or title")

    tasks_root = ROOT / "tasks"
    task_dirs = [p for p in tasks_root.glob("*/*") if p.is_dir()] if tasks_root.exists() else []
    for task in task_dirs:
        if not (task / "spec.md").exists():
            problems.append(f"{task.relative_to(ROOT)}: missing spec.md")

    if problems:
        for item in problems:
            print(f"validate: {item}", file=sys.stderr)
        return EXIT_CHECK_FAILED

    if not quiet:
        print(f"validate: {len(schemas)} schema(s) valid, {len(task_dirs)} task package(s) checked")
    return EXIT_OK


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.path)
    planned = [
        "README.md",
        "pyproject.toml",
        "tasks/",
        "experiments/trackA.yaml",
        "schemas/run.schema.json",
    ]
    if args.dry_run:
        print(f"bendeda init {target}: would create {len(planned)} path(s)")
        for item in planned:
            print(f"  {item}")
        return EXIT_OK
    target.mkdir(parents=True, exist_ok=True)
    for item in planned:
        path = target / item
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
        else:
            path.mkdir(exist_ok=True)
    print(f"bendeda init: scaffolded {target} ({len(planned)} paths)")
    return EXIT_OK


def cmd_task_new(args: argparse.Namespace) -> int:
    task_dir = ROOT / "tasks" / args.tier.lower() / args.name
    files = [
        "spec.md",
        "model.bend",
        "LAWS.bend",
        "laws.manifest.yaml",
        "abs.yaml",
        "props_locked.sv",
        "PROOF_ref.bend",
        "provenance.yaml",
        "variants.yaml",
    ]
    if args.dry_run:
        print(f"bendeda task new: would create {task_dir.relative_to(ROOT)} with {len(files)} files")
        return EXIT_OK
    if task_dir.exists() and not args.force:
        print(f"bendeda task new: {task_dir} already exists (use --force)", file=sys.stderr)
        return EXIT_USAGE
    task_dir.mkdir(parents=True, exist_ok=True)
    for name in files:
        (task_dir / name).touch()
    print(f"bendeda task new: created {task_dir.relative_to(ROOT)} (empty files, status draft)")
    print("  next: fill spec.md, then run the law-authoring gates LA1-LA9")
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    return validate_all(quiet=args.quiet)


def cmd_canary(args: argparse.Namespace) -> int:
    """Run the checker's negative controls and score the verdicts."""
    from bendeda import canary

    checker = canary.build_checker(
        local=args.local,
        root=ROOT,
        bun=args.bun,
        bend_cli=args.bend_cli,
        image=args.image,
        docker=args.docker,
        mode=args.mode,
    )
    if isinstance(checker, str):
        print(f"bendeda canary: cannot run the checker: {checker}", file=sys.stderr)
        print("  nothing was measured, so this is not a pass (exit 3).", file=sys.stderr)
        return EXIT_NOT_IMPLEMENTED

    controls = canary.select(args.family, args.only)
    if not controls:
        print("bendeda canary: no control matched --family or --only", file=sys.stderr)
        return EXIT_USAGE

    workdir = ROOT / ".bend-cache" / "canary"
    if not args.quiet:
        print(
            f"canary: {len(controls)} controls through {checker.label} ({checker.mode} checker)",
            file=sys.stderr,
        )
    result = canary.run_suite(controls, checker, workdir, timeout=args.timeout)

    if args.out:
        canary.write_report(result, Path(args.out))
    if args.json:
        print(json.dumps(result.as_json(), indent=2))
    elif not args.quiet:
        print(canary.format_table(result))

    canary.print_failures(result)
    summary = (
        f"canary: {result.negatives_run} negative controls run, "
        f"{len(result.false_accepts)} false accepts, "
        f"{len(result.false_rejects)} false rejects, "
        f"{len(result.misplaced)} refused at the wrong stage, "
        f"{len(result.unavailable)} unavailable, "
        f"{result.law_stage} refused at the law layer"
    )
    print(summary, file=sys.stderr if result.exit_code() else sys.stdout)
    if result.exit_code() == 1:
        print("canary: a false accept blocks every Bend arm (issue #9).", file=sys.stderr)
    return result.exit_code()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bendeda",
        description="Harness for evaluating Bend 2 laws and proof gates in agentic EDA.",
        epilog="Commands marked (planned) exit non-zero on purpose: nothing silently passes.",
    )
    parser.add_argument("--version", action="version", version=f"bendeda {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_init = sub.add_parser("init", help="scaffold an experiment or task repository")
    p_init.add_argument("path", nargs="?", default=".")
    p_init.add_argument("--dry-run", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_task = sub.add_parser("task", help="task package operations")
    task_sub = p_task.add_subparsers(dest="task_command", metavar="<subcommand>")
    p_task_new = task_sub.add_parser("new", help="create a task package skeleton")
    p_task_new.add_argument("name")
    p_task_new.add_argument("--tier", default="A", choices=["A", "B", "C"])
    p_task_new.add_argument("--force", action="store_true")
    p_task_new.add_argument("--dry-run", action="store_true")
    p_task_new.set_defaults(func=cmd_task_new)

    p_validate = sub.add_parser("validate", help="validate schemas and task packages")
    p_validate.add_argument("--all", action="store_true", help="validate everything (default)")
    p_validate.add_argument("--quiet", action="store_true")
    p_validate.set_defaults(func=cmd_validate)

    p_law = sub.add_parser("law", help="law authoring operations")
    law_sub = p_law.add_subparsers(dest="law_command", metavar="<subcommand>")
    for name, plan, phase in [
        ("lint", "apply rules L001-L015 to a law set and its manifest", "Phase 0.8"),
        ("mutate", "mutate the model and report which laws are falsified (LA3)", "Phase 0.8"),
        ("translate", "translate laws to SVA via templates and emit a TF plan", "Phase 1.6"),
        ("provenance", "verify the authoring chain in provenance.yaml (Appendix J.4)", "Phase 1"),
    ]:
        sp = law_sub.add_parser(name, help=plan)
        sp.add_argument("paths", nargs="*")
        sp.add_argument("--to", default="sva", choices=["sva", "psl"])
        sp.add_argument("--abs", default=None)
        sp.add_argument("--json", action="store_true")
        sp.set_defaults(func=lambda _a, n=name, pl=plan, ph=phase: _todo(f"law {n}", pl, ph))

    p_tf = sub.add_parser("tf", help="translation-fidelity operations")
    tf_sub = p_tf.add_subparsers(dest="tf_command", metavar="<subcommand>")
    sp = tf_sub.add_parser("run", help="compute translation fidelity for a task")
    sp.add_argument("task", nargs="?")
    sp.add_argument("--all", action="store_true")
    sp.set_defaults(func=lambda _a: _todo("tf run", "10k traces per law, verdict agreement", "Phase 1.7"))

    p_canary = sub.add_parser("canary", help="run the checker negative-control suite")
    p_canary.add_argument("--image", default="pinned", help="checker image (default: the pinned Bend image)")
    p_canary.add_argument("--docker", default="docker")
    p_canary.add_argument("--local", action="store_true",
                          help="use the pinned sources under Bun instead of the image")
    p_canary.add_argument("--bun", default=None, help="Bun binary for --local")
    p_canary.add_argument("--bend-cli", default=None, help="bend2/main.ts at the pinned commit for --local")
    p_canary.add_argument("--mode", choices=["default", "verdict"], default="default")
    p_canary.add_argument("--verdict", dest="mode", action="store_const", const="verdict",
                          help="run the same controls through the proven-kernel checker")
    p_canary.add_argument("--only", action="append", default=None, help="run these control ids only")
    p_canary.add_argument("--family", action="append", default=None, help="run these families only")
    p_canary.add_argument("--out", default=None, help="write the full report as JSON")
    p_canary.add_argument("--json", action="store_true")
    p_canary.add_argument("--timeout", type=int, default=180, help="per-control timeout in seconds")
    p_canary.add_argument("--quiet", action="store_true")
    p_canary.set_defaults(func=cmd_canary)

    p_gate = sub.add_parser("gate", help="gate operations")
    gate_sub = p_gate.add_subparsers(dest="gate_command", metavar="<subcommand>")
    sp = gate_sub.add_parser("run", help="run one gate on an artifact directory")
    sp.add_argument("name")
    sp.add_argument("--artifacts", default=".")
    sp.set_defaults(func=lambda _a: _todo("gate run", "lint/sim/formal/conformance gate runner", "Phase 2"))
    sp = gate_sub.add_parser("calibrate", help="gate sensitivity and specificity")
    sp.add_argument("--corpus", default="bugs/")
    sp.set_defaults(func=lambda _a: _todo("gate calibrate", "GS and GSp over the bug corpus", "Phase 1.7"))

    p_run = sub.add_parser("run", help="execute an experiment matrix")
    p_run.add_argument("experiment")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.set_defaults(func=lambda _a: _todo("run", "arm x task x model x seed matrix with budgets", "Phase 2"))

    p_replay = sub.add_parser("replay", help="replay a run from its event log")
    p_replay.add_argument("run_id")
    p_replay.set_defaults(func=lambda _a: _todo("replay", "deterministic replay from events.jsonl", "Phase 2"))

    p_oracle = sub.add_parser("oracle", help="sealed-oracle operations")
    oracle_sub = p_oracle.add_subparsers(dest="oracle_command", metavar="<subcommand>")
    for name, plan, phase in [
        ("seal", "build the deterministic archive and publish a commitment", "Phase 0.10"),
        ("verify-commitment", "check plaintext against the committed Merkle root", "Phase 0.10"),
        ("score", "score a run against the sealed pack (scoring host only)", "Phase 2"),
    ]:
        sp = oracle_sub.add_parser(name, help=plan)
        sp.add_argument("paths", nargs="*")
        sp.set_defaults(func=lambda _a, n=name, pl=plan, ph=phase: _todo(f"oracle {n}", pl, ph))

    p_report = sub.add_parser("report", help="generate tables, plots and the results bundle")
    p_report.add_argument("experiment")
    p_report.set_defaults(func=lambda _a: _todo("report", "primary/secondary tables, forest plots, bundle", "Phase 6"))

    p_bundle = sub.add_parser("bundle", help="proof-carrying design bundle operations")
    bundle_sub = p_bundle.add_subparsers(dest="bundle_command", metavar="<subcommand>")
    sp = bundle_sub.add_parser("verify", help="re-run checks for a bundle")
    sp.add_argument("path")
    sp.set_defaults(func=lambda _a: _todo("bundle verify", "re-check laws, TF and gates in the pinned image", "Phase 2"))

    p_conf = sub.add_parser("conformance", help="conformance rungs that need no EDA toolchain")
    conf_sub = p_conf.add_subparsers(dest="conformance_command", metavar="<subcommand>")
    sp = conf_sub.add_parser("compile", help="compile a Bend model to an ES module")
    sp.add_argument("--model", required=True)
    sp.add_argument("--out", required=True)
    sp.add_argument("--bend-cli", default=None, help="path to bend2/main.ts at the pinned commit")
    sp.add_argument("--bun", default=None)
    sp.set_defaults(func=conformance.cmd_compile)

    sp = conf_sub.add_parser("trace", help="compare compiled model output against a DUT cycle by cycle")
    sp.add_argument("--module", required=True)
    sp.add_argument("--cycles", type=int, default=24)
    sp.add_argument("--driver", default="tools/model_vectors.mjs")
    sp.add_argument("--node", default="node")
    sp.add_argument("--dut", choices=["stub", "verilator"], default="stub",
                    help="stub: Python reference; verilator: real RTL in the pinned image")
    sp.add_argument("--rtl", default=None, help="RTL for --dut verilator")
    sp.add_argument("--spec", default=str(conformance.DEFAULT_SPEC),
                    help="port manifest for the generated testbench (--dut verilator)")
    sp.add_argument("--plan", default=None,
                    help="stimulus plan JSON; per-input sequences live under \"stimulus\"")
    sp.add_argument("--image", default=conformance.DEFAULT_IMAGE, help="simulator image for --dut verilator")
    sp.add_argument("--docker", default="docker")
    sp.add_argument("--sim-timeout", type=int, default=900)
    sp.add_argument("--inject-offset", type=int, default=0, help="self-test: shift the DUT and expect detection")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=conformance.cmd_trace)

    p_serve = sub.add_parser("serve", help="expose tools as MCP or REST")
    p_serve.add_argument("--mcp", action="store_true")
    p_serve.add_argument("--rest", action="store_true")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=lambda _a: _todo("serve", "bend-mcp, hdl-mcp, policy-proxy transports", "Phase 2"))

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_OK
    if not hasattr(args, "func"):
        parser.print_help()
        return EXIT_USAGE
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
