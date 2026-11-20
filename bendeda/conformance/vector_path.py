# SPDX-License-Identifier: Apache-2.0
"""The L1 vector path, executable half (design document §4.2, Appendix K G-03).

Three steps, each testable on its own:

1. `compile_model` — `bend model.bend -o model.mjs`, at a pinned compiler commit.
2. `run_vectors`   — drive the emitted ES module from Node with a stimulus plan.
3. `compare`       — diff model output against a DUT and, when it differs, say
                     *how*: a one-cycle offset is a different defect from a wrong
                     value, and conflating them is how trace conformance turns
                     into a shrug.

The DUT here is a Python cycle-accurate stub. That is deliberate: it proves the
path (compile -> execute -> compare -> detect) without pretending a simulator ran.
The cocotb adapter arrives with the EDA image, and until it does the CLI says so.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DRIVER = Path("tools/model_vectors.mjs")
SATURATION = 15


@dataclass(frozen=True)
class CompileResult:
    ok: bool
    output: Path | None
    stdout: str
    stderr: str


@dataclass(frozen=True)
class Comparison:
    total: int
    mismatches: tuple[int, ...]
    detected_offset: int
    model_steps: tuple[int, ...]
    dut_steps: tuple[int, ...]

    @property
    def matches(self) -> bool:
        return self.total > 0 and not self.mismatches

    @property
    def first_divergence(self) -> int | None:
        return self.mismatches[0] if self.mismatches else None

    def explain(self) -> str:
        if self.total == 0:
            return "no cycles compared"
        if self.matches:
            return f"{self.total} cycles agree"
        if self.detected_offset:
            return (
                f"offset detected: the DUT is {self.detected_offset} cycle(s) "
                f"away from the model; first divergence at cycle {self.first_divergence}"
            )
        return f"value mismatch at cycle {self.first_divergence} ({len(self.mismatches)} of {self.total})"


def to_local_path(value: str | os.PathLike[str]) -> Path:
    """Translate an MSYS/Git-Bash path to a Windows one.

    A path like `/c/Users/x` is meaningful to bash and to nothing else; Python's
    `Path` and `CreateProcess` both reject it. Contributors on Windows paste such
    paths into the environment, so the harness normalises instead of failing.
    """
    text = str(value)
    if os.name == "nt" and re.match(r"^/[a-zA-Z]/", text):
        return Path(f"{text[1].upper()}:/{text[3:]}")
    return Path(text)


def resolve_bun(bun: str | None) -> str | None:
    """Return a spawnable Bun executable.

    npm installs a shell shim at `node_modules/.bin/bun`. On Windows that shim is
    not a PE file, so `subprocess` fails with WinError 193 while the same path
    works from a shell. Resolving to the real binary here keeps the harness
    portable without every caller knowing about npm's layout.
    """
    if not bun:
        return None
    path = to_local_path(bun)
    candidates = [path]
    if path.suffix.lower() != ".exe":
        candidates.append(path.with_suffix(".exe"))
    for parent in (path.parent, path.parent.parent):
        candidates.append(parent / "bun" / "bin" / "bun.exe")
        candidates.append(parent / "bun.exe")
    for candidate in candidates:
        if candidate.is_file() and (os.name != "nt" or candidate.suffix.lower() == ".exe"):
            return str(candidate)
    found = shutil.which(bun)
    if found and (os.name != "nt" or found.lower().endswith(".exe")):
        return found
    return None


def saturating_dut(count: int, inc: int) -> int:
    """The fixture's golden behaviour: min(count + inc, 15)."""
    return min(count + inc, SATURATION)


def compile_model(
    model: Path,
    out: Path,
    bend_cli: Path,
    bun: str = "bun",
    timeout: int = 180,
) -> CompileResult:
    """Compile a Bend model to an ES module.

    `bend_cli` points at `bend2/main.ts` at the pinned commit. Running the
    compiler from source under Bun is how a Windows or macOS machine can use the
    path at all; the container image uses the released binary instead, and both
    must produce the same module for the same model.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    executable = resolve_bun(bun)
    if not executable:
        return CompileResult(False, None, "", f"no spawnable bun executable (tried {bun!r})")
    try:
        done = subprocess.run(
            [executable, str(bend_cli), str(model), "-o", str(out)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CompileResult(False, None, "", f"{type(exc).__name__}: {exc}")
    ok = done.returncode == 0 and out.exists()
    return CompileResult(ok, out if ok else None, done.stdout, done.stderr)


def run_vectors(
    module: Path,
    plan: dict,
    driver: Path = DEFAULT_DRIVER,
    node: str = "node",
    timeout: int = 120,
) -> dict:
    """Execute the emitted module and return the driver's JSON."""
    plan_path = module.with_suffix(".plan.json")
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    done = subprocess.run(
        [node, str(driver), str(module), str(plan_path)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if done.returncode != 0:
        raise RuntimeError(f"vector driver failed ({done.returncode}): {done.stderr.strip()}")
    return json.loads(done.stdout)


def compare(
    steps: list[dict],
    dut=saturating_dut,
    count0: int = 0,
    max_offset: int = 3,
    inject_offset: int = 0,
) -> Comparison:
    """Diff model cycle outputs against the DUT.

    `inject_offset` shifts the DUT's answers forward, which is how the acceptance
    criterion "detects an injected one-cycle offset" is checked.
    """
    model_steps: list[int] = [int(step["out"]) for step in steps]

    dut_steps: list[int] = []
    count = count0
    for step in steps:
        count = dut(count, int(step["inc"]))
        dut_steps.append(count)
    if inject_offset:
        pad = [dut_steps[0]] * inject_offset if dut_steps else []
        dut_steps = pad + dut_steps[: max(0, len(dut_steps) - inject_offset)]

    def mismatch_count(offset: int) -> tuple[int, tuple[int, ...]]:
        bad: list[int] = []
        for index, expected in enumerate(model_steps):
            other = index + offset
            if other >= len(dut_steps) or dut_steps[other] != expected:
                bad.append(index)
        return len(bad), tuple(bad)

    best_offset, best_bad = 0, mismatch_count(0)[1]
    for offset in range(1, max_offset + 1):
        count_bad, bad = mismatch_count(offset)
        if count_bad < len(best_bad):
            best_offset, best_bad = offset, bad

    return Comparison(
        total=len(model_steps),
        mismatches=best_bad,
        detected_offset=best_offset if best_bad else 0,
        model_steps=tuple(model_steps),
        dut_steps=tuple(dut_steps),
    )


def default_plan(cycles: int) -> dict:
    """A stimulus plan that exercises saturation without needing a simulator."""
    incs = [1, 2, 3, 1, 4, 2, 1, 3]
    return {
        "count0": 0,
        "incs": (incs * ((cycles // len(incs)) + 1))[:cycles],
        "entries": ["step", "run"],
    }


def find_bend_toolchain() -> tuple[str | None, Path | None]:
    """Locate Bun and the pinned compiler source, or explain what is missing.

    Resolution order: explicit environment variables first (CI and the container
    set them), then the local cache the development notes describe.
    """
    bun = resolve_bun(os.environ.get("BENDEDA_BUN")) or resolve_bun(shutil.which("bun"))
    cli_env = os.environ.get("BENDEDA_BEND_CLI")
    if cli_env:
        cli = to_local_path(cli_env)
        return (bun, cli if cli.exists() else None)
    for candidate in (
        Path(".bend-cache/bend-2.0.40/bend2/main.ts"),
        Path(os.environ.get("BEND_HOME", "")) / "bend2" / "main.ts",
        Path.home() / ".bend" / "bend2" / "main.ts",
    ):
        if candidate.exists():
            return (bun, candidate)
    return (bun, None)


def cmd_compile(args) -> int:
    bun, cli = find_bend_toolchain()
    bun = resolve_bun(args.bun) or bun
    cli = to_local_path(args.bend_cli) if args.bend_cli else cli
    if not cli or not Path(cli).exists():
        print("conformance compile: no Bend compiler source found", file=sys.stderr)
        print("  set BENDEDA_BEND_CLI=/path/to/bend2/main.ts (pinned commit), or run the container", file=sys.stderr)
        return 3
    if not bun:
        print("compile needs bun (BENDEDA_BUN), or use the bend container", file=sys.stderr)
        return 3
    result = compile_model(Path(args.model), Path(args.out), Path(cli), bun)
    if not result.ok:
        print("conformance compile: failed", file=sys.stderr)
        print((result.stderr or result.stdout).strip()[:2000], file=sys.stderr)
        return 1
    print(f"conformance compile: wrote {result.output}")
    return 0


def cmd_trace(args) -> int:
    module = Path(args.module)
    if not module.exists():
        print(f"conformance trace: no module at {module} (run `bendeda conformance compile` first)", file=sys.stderr)
        return 3
    plan = default_plan(args.cycles)
    try:
        payload = run_vectors(module, plan, driver=Path(args.driver), node=args.node)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"conformance trace: {exc}", file=sys.stderr)
        return 1

    comparison = compare(
        payload["steps"],
        count0=plan["count0"],
        inject_offset=args.inject_offset,
    )
    report = {
        "module": str(module),
        "cycles": comparison.total,
        "matches": comparison.matches,
        "detected_offset": comparison.detected_offset,
        "first_divergence": comparison.first_divergence,
        "mismatches": len(comparison.mismatches),
        "injected_offset": args.inject_offset,
        "exports": payload.get("exports", []),
        "convention": payload.get("convention"),
        "runtime": payload.get("runtime"),
        "model_steps": list(comparison.model_steps),
        "dut_steps": list(comparison.dut_steps),
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"module   : {module}")
        print(f"exports  : {', '.join(report['exports']) or '(none)'}")
        print(f"cycles   : {report['cycles']}")
        print(f"result   : {comparison.explain()}")
        if report["model_steps"]:
            print(f"model    : {report['model_steps'][:12]}{' ...' if report['cycles'] > 12 else ''}")

    # The trace gate passes only on agreement with no injected fault. Asking for
    # an injected offset is a self-test of the comparator, so it passes when the
    # offset IS detected.
    if args.inject_offset:
        detected = comparison.detected_offset == args.inject_offset
        if not args.json:
            print(f"self-test: injected offset {args.inject_offset} -> {'detected' if detected else 'MISSED'}")
        return 0 if detected else 1
    return 0 if comparison.matches else 1
