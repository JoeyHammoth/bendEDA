# SPDX-License-Identifier: Apache-2.0
"""Run the canary controls through the real checker and score the verdicts.

Three outcomes are possible per control and they are deliberately not collapsed:

  accept       the checker printed ALL PROOFS CHECK
  refuse       the checker printed SOME PROOFS FAIL, with a stage saying why
  unavailable  the checker could not run at all (no compiler, no kernel)

An `unavailable` control is not a pass. A suite in which nothing ran reports exit
code 3 and says so, because a skipped gate that looks green is the failure this
programme exists to study.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from bendeda.canary.controls import ANY, ACCEPT, REFUSE, Control
from bendeda.plugins.interfaces import CanaryReport

PASS = "ALL PROOFS CHECK"
FAIL = "SOME PROOFS FAIL"
KERNEL_MISSING = "kernel did not build"

DEFAULT_BEND_IMAGE = "bendeda/bend:2.0.40"
DEFAULT_BEND_CLI = ".bend-cache/bend-2.0.40/bend2/main.ts"
WORK_ROOT = ".bend-cache/canary"

#: Order matters: the first pattern that matches names the stage.
_STAGE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("todo", re.compile(r"TODO found")),
    ("termination", re.compile(r"a call smaller than")),
    ("undefined", re.compile(r"expected : a defined name")),
    # Bend checks defs in file order, so a law used before its proof is reached
    # is refused by a different rule than an unknown name.
    ("order", re.compile(r"checked in file order")),
    # The note is printed only when the checker compared the two sides of the
    # equation, which is what makes a refusal evidence about the law itself.
    ("law", re.compile(r"left side of the equality is the expected")),
    # Without that note the checker never compared two values: it rejected a
    # term because the term had the wrong type. Bend prints `- expected : {}`
    # for a proof that evaluated instead of proving, and `- expected : Nat` for
    # a claim annotated with the wrong type.
    ("type", re.compile(r"^\s*- expected : ", re.MULTILINE)),
)

_STAGES_REFUSAL = {name for name, _ in _STAGE_PATTERNS} | {"front-end"}


def stage_of(output: str) -> str:
    for name, pattern in _STAGE_PATTERNS:
        if pattern.search(output):
            return name
    return "front-end"


@dataclass(frozen=True)
class Checker:
    """How to invoke the pinned checker. `cwd` is the root the paths are relative to."""

    argv: Sequence[str]
    cwd: Path
    label: str
    mode: str = "default"  # default | verdict
    #: The container image, when the checker runs in one. Bare `<image>:<tag>` in
    #: `label` identifies what was asked for; a digest is what identifies what ran.
    image: str | None = None

    def command(self, relative: str) -> list[str]:
        argv = list(self.argv) + [relative]
        if self.mode == "verdict":
            argv.append("--verdict")
        return argv


@dataclass(frozen=True)
class Outcome:
    id: str
    family: str
    defect: str
    expected: str
    expected_stage: str
    actual: str  # accept | refuse | unavailable | error
    stage: str | None
    evidence: str
    command: str

    @property
    def false_accept(self) -> bool:
        return self.expected == REFUSE and self.actual == "accept"

    @property
    def false_reject(self) -> bool:
        return self.expected == ACCEPT and self.actual == "refuse"

    @property
    def misplaced(self) -> bool:
        """Refused, but not where the control was designed to be refused."""
        if self.expected != REFUSE or self.actual != "refuse":
            return False
        if self.expected_stage == ANY:
            return False
        return self.stage != self.expected_stage

    @property
    def unhappy(self) -> bool:
        return self.false_accept or self.false_reject or self.misplaced or self.actual in ("error", "unavailable")


@dataclass
class SuiteResult:
    checker: str
    mode: str
    outcomes: list[Outcome] = field(default_factory=list)

    # --- counters -----------------------------------------------------------
    @property
    def false_accepts(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.false_accept]

    @property
    def false_rejects(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.false_reject]

    @property
    def misplaced(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.misplaced]

    @property
    def unavailable(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.actual == "unavailable"]

    @property
    def errors(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.actual == "error"]

    @property
    def negatives_run(self) -> int:
        return sum(1 for o in self.outcomes if o.expected == REFUSE and o.actual in ("accept", "refuse"))

    @property
    def law_stage(self) -> int:
        return sum(1 for o in self.outcomes if o.actual == "refuse" and o.stage == "law")

    def report(self) -> CanaryReport:
        notes = []
        if self.unavailable:
            notes.append(f"{len(self.unavailable)} control(s) unavailable")
        if self.errors:
            notes.append(f"{len(self.errors)} control(s) produced no verdict")
        if self.misplaced:
            notes.append(f"{len(self.misplaced)} control(s) refused at the wrong stage")
        return CanaryReport(
            false_accepts=len(self.false_accepts),
            false_rejects=len(self.false_rejects),
            controls_run=self.negatives_run,
            notes=tuple(notes),
        )

    def exit_code(self) -> int:
        """0 clean, 1 any disagreement, 3 nothing could be measured."""
        if self.outcomes and len(self.unavailable) == len(self.outcomes):
            return 3
        if self.false_accepts or self.false_rejects or self.misplaced or self.errors:
            return 1
        if not self.outcomes:
            return 3
        return 0

    def as_json(self, environment: Mapping[str, str] | None = None) -> dict:
        payload = {
            "checker": self.checker,
            "mode": self.mode,
            "controls": [o.__dict__ for o in self.outcomes],
            "summary": {
                "controls": len(self.outcomes),
                "negatives_run": self.negatives_run,
                "law_stage_refusals": self.law_stage,
                "false_accepts": len(self.false_accepts),
                "false_rejects": len(self.false_rejects),
                "misplaced": len(self.misplaced),
                "unavailable": len(self.unavailable),
                "errors": len(self.errors),
                "ok": self.exit_code() == 0,
            },
        }
        if environment is not None:
            payload["environment"] = dict(environment)
        return payload


def build_checker(
    *,
    local: bool,
    root: Path,
    bun: str | None = None,
    bend_cli: str | None = None,
    image: str = DEFAULT_BEND_IMAGE,
    docker: str = "docker",
    mode: str = "default",
) -> Checker | str:
    """Return a Checker, or a sentence saying why the checker cannot be run."""
    if local:
        bun_bin = bun or os.environ.get("BENDEDA_BUN") or shutil.which("bun")
        cli = bend_cli or os.environ.get("BENDEDA_BEND_CLI") or DEFAULT_BEND_CLI
        if not bun_bin:
            return "no Bun runner: pass --bun or set BENDEDA_BUN"
        if not (Path(bun_bin).exists() or shutil.which(bun_bin)):
            return f"no Bun runner at {bun_bin}"
        cli_path = Path(cli)
        if not cli_path.is_absolute():
            cli_path = root / cli
        if not cli_path.exists():
            return f"pinned compiler sources are absent: {cli_path} (run tools/fetch_bend.py)"
        return Checker([bun_bin, str(cli_path)], root, f"bun {bun_bin} {cli_path.name}", mode)

    if not (Path(docker).exists() or shutil.which(docker)):
        return f"no {docker} on PATH, and the pinned image is the default checker"
    if image in ("pinned", ""):
        image = DEFAULT_BEND_IMAGE
    return Checker(
        [docker, "run", "--rm", "-v", f"{root}:/work", "-w", "/work", image],
        root,
        image,
        mode,
        image=image,
    )


def _run(argv: Sequence[str], cwd: Path, timeout: int) -> tuple[int, str]:
    try:
        completed = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return completed.returncode, completed.stdout + completed.stderr
    except OSError:
        # The npm Bun on Windows is a POSIX shim, not a PE image. CI is Linux and
        # never takes this path; a local run must still work.
        shell = " ".join(shlex.quote(part) for part in argv)
        # The shim is an MSYS bash on Windows, and it rewrites arguments that
        # look like POSIX paths: `-w /work` reached Docker as
        # `C:/Program Files/Git/work` and the container refused to start. The
        # argv is ours and already absolute, so conversion must be off.
        completed = subprocess.run(
            ["bash", "-c", shell],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "MSYS2_ARG_CONV_EXCL": "*"},
        )
        return completed.returncode, completed.stdout + completed.stderr
    except subprocess.TimeoutExpired:
        return 124, "canary: the checker did not finish within the timeout"


#: Public alias: `law mutate` reuses the same invocation path as the canary suite,
#: so a checker that needs a shell shim behaves the same in both gates.
run_argv = _run


def run_control(
    control: Control,
    checker: Checker,
    workdir: Path,
    timeout: int = 180,
    invoke: Callable[[Sequence[str], Path, int], tuple[int, str]] = _run,
) -> Outcome:
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / f"{control.id}_{control.family}.bend"
    path.write_text(control.source, encoding="utf-8", newline="")
    try:
        relative = path.relative_to(checker.cwd).as_posix()
    except ValueError:
        relative = path.as_posix()

    argv = checker.command(relative)
    rc, output = invoke(argv, checker.cwd, timeout)
    shown = " ".join(shlex.quote(part) for part in argv)

    if KERNEL_MISSING in output:
        return Outcome(control.id, control.family, control.defect, control.expected,
                       control.stage, "unavailable", None, _first(output), shown)
    if PASS in output:
        return Outcome(control.id, control.family, control.defect, control.expected,
                       control.stage, "accept", None, _first(output), shown)
    if FAIL in output:
        stage = stage_of(output)
        return Outcome(control.id, control.family, control.defect, control.expected,
                       control.stage, "refuse", stage, _first(output, after=FAIL), shown)
    if rc == 124:
        return Outcome(control.id, control.family, control.defect, control.expected,
                       control.stage, "error", None, output.strip()[:300], shown)
    return Outcome(control.id, control.family, control.defect, control.expected,
                   control.stage, "error", None, _first(output), shown)


def _first(output: str, after: str | None = None) -> str:
    text = output.split(after, 1)[1] if after and after in output else output
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " / ".join(lines[:3])[:400]


def run_suite(
    controls: Iterable[Control],
    checker: Checker,
    workdir: Path,
    timeout: int = 180,
    invoke: Callable[[Sequence[str], Path, int], tuple[int, str]] = _run,
    progress: Callable[[int, int, Control], None] | None = None,
) -> SuiteResult:
    controls = tuple(controls)
    result = SuiteResult(checker.label, checker.mode)
    for index, control in enumerate(controls, start=1):
        if progress:
            progress(index, len(controls), control)
        result.outcomes.append(run_control(control, checker, workdir, timeout, invoke))
    return result


def format_table(result: SuiteResult) -> str:
    lines = ["control  family        expected  actual  stage        defect"]
    for o in result.outcomes:
        lines.append(
            f"{o.id:<8} {o.family:<13} {o.expected:<9} {o.actual:<7} "
            f"{(o.stage or '-'):<12} {o.defect}"
        )
    return "\n".join(lines)


def print_failures(result: SuiteResult) -> None:
    problems = [o for o in result.outcomes if o.unhappy]
    for o in problems:
        label = (
            "FALSE ACCEPT" if o.false_accept
            else "FALSE REJECT" if o.false_reject
            else "WRONG STAGE" if o.misplaced
            else o.actual.upper()
        )
        print(f"canary: {label} {o.id} ({o.family}): {o.defect}", file=sys.stderr)
        print(f"  expected {o.expected} at stage {o.expected_stage}", file=sys.stderr)
        print(f"  actual   {o.actual} at stage {o.stage or '-'}", file=sys.stderr)
        print(f"  evidence {o.evidence}", file=sys.stderr)
        print(f"  command  {o.command}", file=sys.stderr)


def write_report(
    result: SuiteResult, path: Path, environment: Mapping[str, str] | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.as_json(environment), indent=2) + "\n", encoding="utf-8"
    )
