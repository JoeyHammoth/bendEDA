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


def cmd_law_lint(args: argparse.Namespace) -> int:
    """Code arrives late so `bendeda --help` stays dependency-free."""
    from bendeda.laws import lint

    return lint.cmd_lint(args)


def cmd_law_mutate(args: argparse.Namespace) -> int:
    from bendeda.laws import mutate

    return mutate.cmd_mutate(args)


def cmd_oracle_seal(args: argparse.Namespace) -> int:
    from bendeda import oracle

    return oracle.cmd_seal(args)


def cmd_oracle_verify_commitment(args: argparse.Namespace) -> int:
    from bendeda import oracle

    return oracle.cmd_verify_commitment(args)


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

    from bendeda import provenance

    # Criterion 2 of issue #6: a run names the image digest and the version the
    # tool reported. The tag alone cannot distinguish a rebuilt image.
    environment = provenance.environment(checker, args.docker)

    if args.out:
        canary.write_report(result, Path(args.out), environment)
    if args.json:
        print(json.dumps(result.as_json(environment), indent=2))
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


def cmd_replay(args: argparse.Namespace) -> int:
    """Re-decide a proxy audit log against its policy.

    This replays the proxy's decisions, not a whole scored run: a log whose
    decisions no longer follow from its policy is reported at the sequence that
    diverged. Outcome replay and budgets are the rest of #15.
    """
    from bendeda import replay as replay_module
    from bendeda.proxy import Policy

    try:
        policy = Policy.load(args.policy)
        report = replay_module.replay(args.events, policy)
    except (OSError, ValueError) as exc:
        print(f"bendeda replay: {exc}", file=sys.stderr)
        print("  nothing was replayed, so this is not a pass (exit 3).", file=sys.stderr)
        return EXIT_NOT_IMPLEMENTED

    for divergence in report.diverged:
        print(f"replay: diverged {divergence.render()}", file=sys.stderr)
    for problem in report.malformed:
        print(f"replay: malformed {problem}", file=sys.stderr)
    print(
        f"replay: {report.events} event(s), {report.matched} reproduced, "
        f"{len(report.diverged)} diverged, {len(report.malformed)} malformed"
    )
    return report.exit_code()


def cmd_proxy_decide(args: argparse.Namespace) -> int:
    from bendeda.proxy import Policy

    try:
        policy = Policy.load(args.policy)
    except (OSError, ValueError) as exc:
        print(f"bendeda proxy decide: {exc}", file=sys.stderr)
        return EXIT_USAGE
    decision = policy.decide(args.tool, args.resource)
    print(json.dumps(decision.as_json(), indent=2))
    return EXIT_OK if decision.allowed else 1


def cmd_proxy_serve(args: argparse.Namespace) -> int:
    from bendeda.proxy import AuditLog, Policy, serve

    try:
        policy = Policy.load(args.policy)
    except (OSError, ValueError) as exc:
        print(f"bendeda proxy serve: {exc}", file=sys.stderr)
        return EXIT_USAGE
    log = AuditLog(args.events)
    server = serve(policy, log, host=args.host, port=args.port, max_calls=args.max_calls)
    host, port = server.server_address[:2]
    print(
        f"proxy: listening on http://{host}:{port}, default {policy.default}, "
        f"{len(policy.rules)} rule(s), events -> {args.events}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return EXIT_OK


def _runner_spec(args: argparse.Namespace):
    """One spec shape for every runner subcommand, so they cannot drift apart."""
    from bendeda.runner import AgentSpec

    return AgentSpec(
        workspace=Path(args.workspace),
        image=getattr(args, "image", "bendeda/harness:0.0.1"),
        network=args.network,
        policy=Path(args.policy) if getattr(args, "policy", None) else None,
        events=Path(args.events) if getattr(args, "events", None) else None,
    )


def cmd_runner_plan(args: argparse.Namespace) -> int:
    """Print the sandbox commands. Nothing is started: a plan is not a run."""
    import shlex

    from bendeda.runner import Unrunnable, plan

    spec = _runner_spec(args)
    try:
        commands = plan(spec)
    except Unrunnable as exc:
        print(f"bendeda runner plan: {exc}", file=sys.stderr)
        return EXIT_USAGE
    for command in commands:
        print(" ".join(shlex.quote(part) for part in command))
    return EXIT_OK


def cmd_runner_check(args: argparse.Namespace) -> int:
    from bendeda.runner import check

    problems = check(
        args.container,
        args.network,
        Path(args.workspace),
        Path(args.oracle) if args.oracle else None,
    )
    for problem in problems:
        print(f"runner check: {problem}", file=sys.stderr)
    if problems:
        return 1
    print(
        f"runner check: {args.container} is attached only to {args.network} and mounts "
        f"only {args.workspace}"
    )
    return EXIT_OK


def cmd_runner_classify(args: argparse.Namespace) -> int:
    """Scored or excluded, from the event log. A classification is not a pass."""
    from bendeda.budget import Limits, classify, read_log

    try:
        events = read_log(args.events)
    except (OSError, ValueError) as exc:
        print(f"bendeda runner classify: {exc}", file=sys.stderr)
        return EXIT_USAGE
    outcome = classify(events, Limits(calls=args.max_calls))
    print(json.dumps(outcome.as_json(), indent=2))
    return EXIT_OK


def cmd_runner_up(args: argparse.Namespace) -> int:
    """Start the sandbox, or leave nothing behind trying."""
    from bendeda.runner import SandboxError, up

    spec = _runner_spec(args)
    try:
        started = up(spec)
    except (SandboxError, OSError) as exc:
        print(f"bendeda runner up: {exc}", file=sys.stderr)
        return EXIT_USAGE
    print(f"runner up: started {', '.join(started)} on {spec.network}")
    print(f"runner up: the agent mounts only {spec.workspace} and reaches only {spec.events and 'the proxy'}")
    return EXIT_OK


def cmd_runner_exec(args: argparse.Namespace) -> int:
    """Run the arm's command inside the sandbox, then record the submission."""
    from bendeda.runner import exec_enforced, exec_in, submit

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("bendeda runner exec: no command given", file=sys.stderr)
        return EXIT_USAGE
    exhausted = False
    if args.events and args.max_calls:
        result = exec_enforced(
            args.container, command, Path(args.events), args.max_calls, args.wall_min
        )
        code, output, exhausted = result.code, result.output, result.exhausted
        if exhausted:
            print(
                f"runner exec: budget exhausted after {result.calls} call(s) "
                f"({result.stopped}); the sandbox was stopped",
                file=sys.stderr,
            )
    else:
        code, output = exec_in(args.container, command)
    if output.strip():
        print(output.rstrip())
    if exhausted:
        # A spent allowance is a result, not a harness failure: `score` records it as
        # S=0 from the log, and this command does what it says either way.
        return EXIT_OK
    if code != 0:
        return code
    if args.submit:
        code, output = submit(args.container, args.submit)
        if output.strip():
            print(output.rstrip())
        if code != 0:
            print("runner exec: the submission was not recorded", file=sys.stderr)
            return EXIT_CHECK_FAILED
    return EXIT_OK


def cmd_runner_down(args: argparse.Namespace) -> int:
    """Remove the sandbox. Something already gone is not a failure."""
    from bendeda.runner import down

    spec = _runner_spec(args)
    try:
        problems = down(spec)
    except OSError as exc:
        print(f"bendeda runner down: {exc}", file=sys.stderr)
        return EXIT_USAGE
    for problem in problems:
        print(f"runner down: {problem}", file=sys.stderr)
    if problems:
        return EXIT_CHECK_FAILED
    print(f"runner down: removed the agent, the proxy and the network {spec.network}")
    return EXIT_OK


def cmd_gate_run(args: argparse.Namespace) -> int:
    """Re-execute gates on submitted artifacts. A skip is not a pass."""
    from bendeda.gates import GATES, PLANNED, run_gates, skipped, verdicts

    names = list(args.names) or sorted(GATES)
    for name in names:
        if name in PLANNED:
            print(f"gate run: {name}: not implemented yet — {PLANNED[name]}", file=sys.stderr)
    runnable = [name for name in names if name not in PLANNED]
    unknown = [name for name in runnable if name not in GATES]
    if unknown:
        print(f"gate run: unknown gate(s): {', '.join(unknown)}", file=sys.stderr)
        return EXIT_USAGE
    if not runnable:
        return EXIT_NOT_IMPLEMENTED
    try:
        results = run_gates(
            args.artifacts, runnable, {"image": args.image, "cycles": args.cycles}
        )
    except KeyError as exc:
        print(f"gate run: unknown gate {exc.args[0]}", file=sys.stderr)
        return EXIT_USAGE
    if args.json:
        print(json.dumps(
            {
                name: {
                    "status": result.status,
                    "reason": result.reason,
                    "detail": dict(result.detail),
                    "elapsed_ms": result.elapsed_ms,
                }
                for name, result in results.items()
            },
            indent=2,
        ))
    else:
        for name, result in results.items():
            suffix = f" — {result.reason}" if result.reason else ""
            print(f"gate {name}: {result.status}{suffix}")
    if args.out:
        Path(args.out).write_text(
            json.dumps(verdicts(results), indent=2, sort_keys=True), encoding="utf-8"
        )
        print(f"gate run: wrote {args.out}")
    if any(result.status == "fail" for result in results.values()):
        return EXIT_CHECK_FAILED
    if skipped(results):
        return EXIT_NOT_IMPLEMENTED
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    """Expand a matrix and, unless --dry-run, execute cells into scoreable bundles."""
    from bendeda.matrix import execute_cell, expand, load as load_matrix

    try:
        matrix = load_matrix(Path(args.matrix))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"bendeda run: {exc}", file=sys.stderr)
        return EXIT_USAGE
    cells = expand(matrix)
    if args.dry_run:
        for number, cell in enumerate(cells, start=1):
            print(json.dumps({
                "n": number, "cell": cell.label, "task": cell.task.name,
                "arm": cell.arm, "seed": cell.seed,
            }))
        print(f"run: {len(cells)} cell(s) in {matrix.name}; nothing was executed")
        return EXIT_OK

    limit = args.limit or len(cells)
    records = [execute_cell(matrix, cell, args.out) for cell in cells[:limit]]
    for record in records:
        print(json.dumps(
            {key: record[key] for key in ("cell", "S", "V", "O", "complete", "error")},
            sort_keys=True,
        ))
    complete = sum(1 for record in records if record["complete"])
    print(f"run: {len(records)} cell(s), {complete} complete, {len(records) - complete} incomplete")
    print("run: bundles are in " + str(Path(args.out) / matrix.name))
    return EXIT_OK if complete == len(records) else EXIT_NOT_IMPLEMENTED


def cmd_score(args: argparse.Namespace) -> int:
    """S, V and O from a run bundle. A missing result is not a pass."""
    from bendeda.proxy import Policy
    from bendeda.score import load, report

    try:
        bundle = load(Path(args.bundle))
        policy = Policy.load(args.policy) if args.policy else None
    except (OSError, ValueError) as exc:
        print(f"bendeda score: {exc}", file=sys.stderr)
        return EXIT_USAGE
    result = report(bundle, policy)
    print(json.dumps(result.as_json(), indent=2))
    for note in result.notes:
        print(f"score: {note}", file=sys.stderr)
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

    p_lint = law_sub.add_parser("lint", help="apply rules L001-L015 to task packages")
    p_lint.add_argument("paths", nargs="+")
    p_lint.add_argument("--mutation", default=None,
                        help="mutation report from `law mutate`; without it L006 is not evaluated")
    p_lint.add_argument("--recursive", action="store_true",
                        help="search directories for task packages (the default)")
    p_lint.add_argument("--json", action="store_true")
    p_lint.add_argument("--quiet", action="store_true")
    p_lint.set_defaults(func=cmd_law_lint)

    p_mutate = law_sub.add_parser("mutate", help="mutate the model and report which laws are falsified (LA3)")
    p_mutate.add_argument("paths", nargs="+", help="task directory, or the model.bend with --laws")
    p_mutate.add_argument("--laws", default=None, help="LAWS.bend when paths is a model file")
    p_mutate.add_argument("--bv", default=None, help="bv.bend to inline ahead of the laws")
    p_mutate.add_argument("--local", action="store_true",
                          help="use the pinned sources under Bun instead of the image")
    p_mutate.add_argument("--bun", default=None)
    p_mutate.add_argument("--bend-cli", default=None)
    p_mutate.add_argument("--image", default="pinned")
    p_mutate.add_argument("--docker", default="docker")
    p_mutate.add_argument("--min-mutants", type=int, default=20,
                          help="LA3's pre-registered minimum (default 20)")
    p_mutate.add_argument("--min-kill", type=float, default=0.9,
                          help="fraction of mutants at least one law must kill (default 0.9)")
    p_mutate.add_argument("--max-mutants", type=int, default=48)
    p_mutate.add_argument("--timeout", type=int, default=180)
    p_mutate.add_argument("--out", default=None)
    p_mutate.add_argument("--json", action="store_true")
    p_mutate.add_argument("--quiet", action="store_true")
    p_mutate.set_defaults(func=cmd_law_mutate)

    for name, plan, phase in [
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
    sp = gate_sub.add_parser("run", help="re-execute gates on an artifact directory")
    sp.add_argument("names", nargs="*", help="trace, formal (default: every implemented gate)")
    sp.add_argument("--artifacts", default=".")
    sp.add_argument("--image", default="bendeda/oss-cad:2026-11-20")
    sp.add_argument("--cycles", type=int, default=8)
    sp.add_argument("--out", default=None, help="write the pass/fail map (gates.json) here")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_gate_run)
    sp = gate_sub.add_parser("calibrate", help="gate sensitivity and specificity")
    sp.add_argument("--corpus", default="bugs/")
    sp.set_defaults(func=lambda _a: _todo("gate calibrate", "GS and GSp over the bug corpus", "Phase 1.7"))

    p_run = sub.add_parser("run", help="execute an experiment matrix")
    p_run.add_argument("--matrix", required=True, help="matrix JSON (see experiments/README.md)")
    p_run.add_argument("--dry-run", action="store_true", help="expand the cells and execute nothing")
    p_run.add_argument("--limit", type=int, default=0, help="execute only the first N cells")
    p_run.add_argument("--out", default=str(Path(".bend-cache") / "runs"), help="where bundles go")
    p_run.set_defaults(func=cmd_run)

    p_runner = sub.add_parser("runner", help="agent sandbox: plan it, then check it")
    runner_sub = p_runner.add_subparsers(dest="runner_command", metavar="<subcommand>")
    sp = runner_sub.add_parser("plan", help="print the docker commands for the sandbox")
    sp.add_argument("--workspace", default=".")
    sp.add_argument("--image", default="bendeda/harness:0.0.1")
    sp.add_argument("--network", default="bendeda-offline")
    sp.add_argument("--policy", help="proxy policy JSON")
    sp.add_argument("--events", help="audit log path the proxy writes")
    sp.set_defaults(func=cmd_runner_plan)
    sp = runner_sub.add_parser("check", help="verify a running agent container")
    sp.add_argument("container")
    sp.add_argument("--workspace", required=True)
    sp.add_argument("--network", default="bendeda-offline")
    sp.add_argument("--oracle", default=None, help="a path that must not be mounted")
    sp.set_defaults(func=cmd_runner_check)
    sp = runner_sub.add_parser("classify", help="budget exhaustion or exclusion, from a log")
    sp.add_argument("--events", required=True)
    sp.add_argument("--max-calls", type=int, default=400)
    sp.set_defaults(func=cmd_runner_classify)
    sp = runner_sub.add_parser("up", help="start the sandbox: network, proxy, then agent")
    sp.add_argument("--workspace", default=".")
    sp.add_argument("--image", default="bendeda/harness:0.0.1")
    sp.add_argument("--network", default="bendeda-offline")
    sp.add_argument("--policy", required=True, help="proxy policy JSON")
    sp.add_argument("--events", required=True, help="audit log the proxy writes")
    sp.set_defaults(func=cmd_runner_up)
    sp = runner_sub.add_parser("exec", help="run a command inside the agent container")
    sp.add_argument("--container", default="bendeda-agent")
    sp.add_argument("--submit", default=None,
                   help="record a submission for this resource when the command succeeds")
    sp.add_argument("--events", default=None, help="audit log to police a tool-call budget")
    sp.add_argument("--max-calls", type=int, default=0,
                   help="stop the sandbox when the log passes this many calls")
    sp.add_argument("--wall-min", type=float, default=None,
                   help="stop the sandbox after this many minutes")
    sp.add_argument("command", nargs=argparse.REMAINDER, help="the command; prefix with -- if it takes flags")
    sp.set_defaults(func=cmd_runner_exec)
    sp = runner_sub.add_parser("down", help="remove the sandbox's containers and network")
    sp.add_argument("--workspace", default=".")
    sp.add_argument("--network", default="bendeda-offline")
    sp.set_defaults(func=cmd_runner_down)

    p_proxy = sub.add_parser("proxy", help="policy proxy for agent egress")
    proxy_sub = p_proxy.add_subparsers(dest="proxy_command", metavar="<subcommand>")
    sp = proxy_sub.add_parser("serve", help="answer allow/deny for tool calls, and log them")
    sp.add_argument("--policy", required=True, help="policy JSON (deny by default)")
    sp.add_argument("--events", required=True, help="append-only JSONL audit log")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--max-calls", type=int, default=None,
                   help="refuse calls past this allowance with 429 (rule: budget)")
    sp.set_defaults(func=cmd_proxy_serve)
    sp = proxy_sub.add_parser("decide", help="decide one call without a server")
    sp.add_argument("--policy", required=True)
    sp.add_argument("--tool", required=True)
    sp.add_argument("--resource", required=True)
    sp.set_defaults(func=cmd_proxy_decide)

    p_replay = sub.add_parser("replay", help="re-decide a run's tool log")
    p_replay.add_argument("--events", required=True, help="events.jsonl written by the proxy")
    p_replay.add_argument("--policy", required=True, help="the policy the run was governed by")
    p_replay.set_defaults(func=cmd_replay)

    p_score = sub.add_parser("score", help="compute S, V and O for a recorded run")
    p_score.add_argument("--bundle", required=True,
                         help="directory with events.jsonl and optional run/gates/oracle/outcome JSON")
    p_score.add_argument("--policy", default=None,
                         help="also re-decide the tool log against this policy first")
    p_score.set_defaults(func=cmd_score)

    p_oracle = sub.add_parser("oracle", help="sealed-oracle operations")
    oracle_sub = p_oracle.add_subparsers(dest="oracle_command", metavar="<subcommand>")

    p_seal = oracle_sub.add_parser(
        "seal", help="build the deterministic archive and publish a commitment"
    )
    p_seal.add_argument("path", help="plaintext oracle directory (never committed)")
    p_seal.add_argument("--out", default="oracle_sealed", help="where the ciphertext and commitment go")
    p_seal.add_argument("--recipient", default=None,
                       help="age public key; sealing refuses without one")
    p_seal.add_argument("--age", default="age", help="age binary (default: age on PATH)")
    p_seal.add_argument("--dry-run", action="store_true",
                       help="print the Merkle root and write nothing")
    p_seal.add_argument("--json", action="store_true")
    p_seal.set_defaults(func=cmd_oracle_seal)

    p_verify = oracle_sub.add_parser(
        "verify-commitment", help="check plaintext against the committed Merkle root"
    )
    p_verify.add_argument("path", help="plaintext oracle directory")
    p_verify.add_argument("--commitment", required=True, help="commitment.json from `oracle seal`")
    p_verify.set_defaults(func=cmd_oracle_verify_commitment)

    sp = oracle_sub.add_parser("score", help="score a run against the sealed pack (scoring host only)")
    sp.add_argument("paths", nargs="*")
    sp.set_defaults(func=lambda _a: _todo(
        "oracle score", "score a run against the sealed pack (scoring host only)", "Phase 2"
    ))

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
