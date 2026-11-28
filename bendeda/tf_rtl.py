# SPDX-License-Identifier: Apache-2.0
"""The RTL half of translation fidelity (TF), step 3 of the design.

`bendeda/tf.py` evaluates each translated law on the model for one bound trace.
This module produces the other verdict: which assertion in the locked pack fires,
and in which cycle, when the same stimulus is simulated against a design. It is
not `tf run`; a pair is not a TF number until step 4 joins it with the model side.

Why simulation and not another proof: 10,000 traces would be 10,000 proofs, and a
BMC run over free inputs answers a different question (does a counterexample
exist) than a simulation of one trace (does *this* trace violate it). The proof
stays the gate's job (`bendeda/gates.py`'s `formal`); the simulation is the
metric's.

Why Verilator with assertions enabled rather than a re-statement of the pack: the
pack is the artifact that ships, and a second statement of it in Python would
test the second statement. `--assert` makes the immediate assertions in
`props_locked.sv` ordinary runtime checks, and Verilator names the failing
instance (`...u_props.p_pop_full_count`), so both halves of the pair are read from
the simulator's own report.

Three limits are stated rather than hidden:

- One process per trace. A failed assertion stops the simulation, so a second
  violation in the same trace would be invisible; separate processes keep each
  trace's first failure its own. The compile happens once and the binary is run
  per trace, so 10,000 traces are 10,000 simulations of one binary, not 10,000
  Verilator builds.
- `p_reset_empty` is observed only when `rst_n` is actually asserted. The bench
  asserts reset before the first operation and never again, so this module cannot
  report that law. TF needs a reset in the stimulus to exercise it, and inventing
  one here would be a decision step 4 has to make and record.
- The bench deasserts reset after *two* edges, not one. The pack asserts
  `p_reset_empty` on the first cycle after a low `rst_n`, and a design that takes
  its first operation on that very edge would fire the law while behaving to the
  abstraction map's assumption ("reset for at least one rising edge before the
  first operation"). Two idle reset edges satisfy that assumption with room to
  spare; one would make this bench report a disagreement that belongs to the
  pack's start-of-trace convention rather than to the design.

The cycle a failure is attributed to is the trace cycle, not the simulator
iteration. The pack samples the operation and the occupancy at the previous edge
(`*_d`) and observes their result at the current one, so an assertion that fires
in iteration `k` judges the transition of trace cycle `k - 1`; the report keeps
both numbers. That is the pack's documented timing, and the model side
(`bendeda/tf.py`) evaluates a law on the pre-state and operation of one cycle, so
the trace cycle is what the two sides can be compared on.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from bendeda.conformance.vector_path import DEFAULT_IMAGE, _remove_container, validate_spec
from bendeda.laws.manifest import Manifest
from bendeda.runner import _docker_path

TOP = "tb_assert"

#: The pack is instantiated by the submission under this name (`u_props` in
#: `tasks/seq/B1_fifo`'s `dut.sv`), and Verilator's message names the full instance
#: path. Parsing the suffix is how the assertion's label survives without a
#: line-number table that would go stale on any pack edit.
BOUND = "u_props"

ASSERTION = re.compile(r"Assertion failed in \S*?\." + BOUND + r"\.(\w+)")
LABEL = re.compile(r"^\s*(p_\w+)\s*:\s*assert\b", re.MULTILINE)
SOURCE_LINE = re.compile(r"props_locked\.sv:(\d+)")


@dataclass(frozen=True)
class Failure:
    """One assertion, at one cycle, as the simulator reported it."""

    assertion: str
    cycle: int | None
    observed_at: int | None
    line: int | None
    message: str


@dataclass
class TraceVerdict:
    trace: int
    cycles: int
    failure: Failure | None

    @property
    def clean(self) -> bool:
        return self.failure is None

    def as_json(self) -> dict[str, Any]:
        return {
            "trace": self.trace,
            "cycles": self.cycles,
            "clean": self.clean,
            "assertion": self.failure.assertion if self.failure else None,
            "cycle": self.failure.cycle if self.failure else None,
            "observed_at": self.failure.observed_at if self.failure else None,
            "line": self.failure.line if self.failure else None,
            "message": self.failure.message if self.failure else None,
        }


@dataclass
class BenchReport:
    """Every trace's RTL-side verdict, and the image that produced them."""

    image: str
    image_id: str | None
    declared: list[str]
    verdicts: list[TraceVerdict] = field(default_factory=list)

    @property
    def failures(self) -> list[TraceVerdict]:
        return [verdict for verdict in self.verdicts if not verdict.clean]

    @property
    def unobserved(self) -> list[str]:
        """Assertions no trace fired. Not a pass: an unexercised law is a null row."""
        fired = {verdict.failure.assertion for verdict in self.failures if verdict.failure}
        return [label for label in self.declared if label not in fired]

    def as_json(self) -> dict[str, Any]:
        return {
            "side": "rtl",
            "image": self.image,
            "image_id": self.image_id,
            "declared": list(self.declared),
            "traces": [verdict.as_json() for verdict in self.verdicts],
            "tf": None,
            "tf_note": "TF needs the model verdict on the same trace; this run recorded "
                       "the assertion that fired on the RTL side only",
        }


def declared_assertions(props: str | Path) -> list[str]:
    """The assertion labels in a pack, in source order.

    Read from the pack rather than from the manifest: the manifest says which
    label a law *claims*, and the pack says which labels exist. A bench that
    trusts the first cannot notice a translation that never reached the file.
    """
    text = props if isinstance(props, str) else Path(props).read_text(encoding="utf-8")
    return LABEL.findall(text)


def law_by_assertion(manifest: Manifest) -> dict[str, str]:
    """SVA label -> law id, from the declarations the manifest actually carries."""
    return {
        str(entry.translation["sva"]): entry.id
        for entry in manifest.laws
        if entry.translation and entry.translation.get("sva")
    }


def _declaration(item: Mapping[str, Any], kind: str, initial: str | None = None) -> str:
    width = int(item["width"])
    text = f"  {kind} {item['port']}" if width == 1 else f"  {kind} [{width - 1}:0] {item['port']}"
    if initial is not None:
        text += f" = {initial}"
    return text + ";"


def _deasserted(reset: Mapping[str, Any]) -> str:
    # Active-high reset is deasserted low, active-low reset high. Reading the
    # manifest rather than assuming `rst_n` is why the same bench drives either.
    return "1'b0" if reset.get("active_high", True) else "1'b1"


def _asserted(reset: Mapping[str, Any]) -> str:
    return "1'b1" if reset.get("active_high", True) else "1'b0"


def render_bench(
    spec, *, traces: int, cycles: int, reset_cycles: int = 2
) -> str:
    """The SystemVerilog bench: one binary, one trace per process.

    `+trace=<n>` selects a block of `cycles` stimulus words out of `stim.hex`, so
    the compile is shared by every trace. `cycle.txt` records the cycle the
    simulation reached, because a failing assertion stops the process and the
    ordering of the simulator's own streams is not something to depend on.
    """
    spec = validate_spec(spec)
    clock = spec["clock"]
    reset = spec["reset"]
    inputs = spec["inputs"]
    outputs = spec["outputs"]
    clock_port = clock["port"]
    half = max(1, clock["period_ns"] // 2)
    total = sum(item["width"] for item in inputs)

    lines = [
        "// SPDX-License-Identifier: Apache-2.0",
        "// Generated by bendeda.tf_rtl from a port manifest and a stimulus plan.",
        "// Do not edit; regenerate with `bendeda.tf_rtl.render_bench`.",
        "`timescale 1ns/1ps",
        f"module {TOP};",
        f"  reg {clock_port} = 1'b0;",
    ]
    if reset:
        lines.append(_declaration({"port": reset["port"], "width": 1}, "reg", _asserted(reset)))
    for item in inputs:
        lines.append(_declaration(item, "reg", "0"))
    for item in outputs:
        lines.append(_declaration(item, "wire"))
    lines.append("")

    connections = [f"    .{clock_port}({clock_port})"]
    if reset:
        connections.append(f"    .{reset['port']}({reset['port']})")
    for item in inputs + outputs:
        connections.append(f"    .{item['port']}({item['port']})")
    lines += [
        f"  {spec['top']} dut (",
        ",\n".join(connections),
        "  );",
        "",
        f"  always #{half} {clock_port} = ~{clock_port};",
        "",
        f"  reg [{total - 1}:0] stim [0:{traces * cycles - 1}];",
        f"  reg [{total - 1}:0] row;",
        "  integer cycles_arg;",
        "  integer trace;",
        "  integer base;",
        "  integer i;",
        "  integer fd;",
        "",
        "  initial begin",
        '    if (!$value$plusargs("trace=%d", trace)) trace = 0;',
        f'    if (!$value$plusargs("cycles=%d", cycles_arg)) cycles_arg = {cycles};',
        '    $readmemh("stim.hex", stim);',
        '    fd = $fopen("cycle.txt", "w");',
        "    if (fd == 0) begin",
        '      $display("tf_rtl: cannot open cycle.txt");',
        "      $finish;",
        "    end",
        "    base = trace * cycles_arg;",
    ]
    if reset:
        lines += [
            f"    repeat ({reset_cycles}) @(posedge {clock_port});",
            f"    #1 {reset['port']} = {_deasserted(reset)};",
        ]
    lines += [
        "    for (i = 0; i < cycles_arg; i = i + 1) begin",
        "      row = stim[base + i];",
    ]
    offset = 0
    for item in inputs:
        lines.append(f"      {item['port']} = row[{offset} +: {item['width']}];")
        offset += item["width"]
    lines += [
        '      $fdisplay(fd, "%0d", i);',
        "      $fflush(fd);",
        f"      @(posedge {clock_port});",
        "      #1;",
        "    end",
        "    $fclose(fd);",
        '    $display("tf_rtl: trace %0d clean over %0d cycles", trace, cycles_arg);',
        "    $finish;",
        "  end",
        "endmodule",
        "`default_nettype wire",
        "",
    ]
    return "\n".join(lines)


def _cycles_of(spec: Mapping[str, Any], trace: Mapping[str, Sequence[int]]) -> int:
    """One length for a trace, and a refusal rather than a guess for a ragged one."""
    lengths: dict[str, int] = {}
    for item in spec["inputs"]:
        if item["stimulus"] == "const":
            continue
        values = trace.get(item["key"])
        if values is None:
            raise ValueError(f"the trace has no values for input {item['port']!r} (key {item['key']!r})")
        lengths[item["key"]] = len(values)
    if not lengths:
        raise ValueError("the manifest drives every input from a constant; there is no trace to run")
    unique = set(lengths.values())
    if len(unique) != 1:
        raise ValueError(f"the trace's inputs have different lengths: {lengths}")
    cycles = unique.pop()
    if cycles <= 0:
        raise ValueError("the trace is empty, so no cycle would be simulated")
    return cycles


def _words(spec: Mapping[str, Any], trace: Mapping[str, Sequence[int]], cycles: int) -> list[int]:
    """Pack one stimulus word per cycle, in manifest order, least-significant first.

    Deliberately the same packing as `conformance.vector_path.build_stimulus`: the
    trace gate and this bench must drive the same design with the same bits, or a
    disagreement could be a harness difference.
    """
    words: list[int] = []
    for index in range(cycles):
        word = 0
        offset = 0
        for item in spec["inputs"]:
            if item["stimulus"] == "const":
                value = item["value"]
            else:
                value = trace[item["key"]][index]
            word |= (int(value) & ((1 << item["width"]) - 1)) << offset
            offset += item["width"]
        words.append(word)
    return words


def _image_id(docker: str, image: str) -> str | None:
    try:
        done = subprocess.run(
            [docker, "image", "inspect", "--format", "{{.Id}}", image],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    resolved = (done.stdout or "").strip().splitlines()
    if done.returncode == 0 and resolved and resolved[0].startswith("sha256:"):
        return resolved[0]
    return None


def _docker_run(
    work: Path, inner: str, *, image: str, docker: str, timeout: int, name: str
) -> tuple[int, str]:
    command = [docker, "run", "--rm", "--name", name, "-v", f"{_docker_path(work)}:/work", "-w", "/work"]
    if hasattr(os, "getuid"):
        command += ["-u", f"{os.getuid()}:{os.getgid()}"]
    # `bash -c`, never `bash -lc`: a login shell rewrites PATH and loses the image's
    # /opt/oss-cad-suite/bin, which is where verilator lives (same note as the
    # vector path, for the same measured reason).
    command += [image, "bash", "-c", inner]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _remove_container(docker, name)
        raise RuntimeError(f"the simulation did not finish within {timeout}s") from exc
    except OSError as exc:
        raise RuntimeError(f"cannot run {docker!r}: {exc}") from exc
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def _tail(text: str, limit: int = 800) -> str:
    lines = [line for line in (text or "").strip().splitlines() if line.strip()]
    return " | ".join(lines[-3:])[:limit] if lines else "(no output)"


def _last_cycle(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip().splitlines()[-1])
    except (OSError, ValueError, IndexError):
        return None


def run_assertions(
    dut: str | Path,
    props: str | Path,
    spec,
    traces: Sequence[Mapping[str, Sequence[int]]],
    *,
    image: str = DEFAULT_IMAGE,
    docker: str = "docker",
    reset_cycles: int = 2,
    build_timeout: int = 900,
    run_timeout: int = 300,
) -> BenchReport:
    """Compile the pack against `dut` once, then simulate each trace in its own process.

    `traces` are per-input sequences (`{"push": [...], "pop": [...], "din": [...]}`),
    the same shape a `plan.json` calls `stimulus`. Every trace must be the same
    length; a ragged stimulus is refused rather than truncated.
    """
    spec = validate_spec(spec)
    if not traces:
        raise ValueError("no traces: nothing would be simulated")
    cycles = _cycles_of(spec, traces[0])
    for index, trace in enumerate(traces[1:], start=1):
        if _cycles_of(spec, trace) != cycles:
            raise ValueError(f"trace {index} has a different length from trace 0")

    declared = declared_assertions(Path(props).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="bendeda-tf-rtl-") as raw:
        work = Path(raw)
        shutil.copyfile(dut, work / "dut.sv")
        shutil.copyfile(props, work / "props_locked.sv")
        (work / "tb_assert.sv").write_text(
            render_bench(spec, traces=len(traces), cycles=cycles, reset_cycles=reset_cycles),
            encoding="utf-8",
            newline="\n",
        )
        words = [word for trace in traces for word in _words(spec, trace, cycles)]
        (work / "stim.hex").write_text(
            "\n".join(f"{word:x}" for word in words) + "\n", encoding="utf-8", newline="\n"
        )
        build = (
            f"verilator --binary --timing -Wno-fatal -j 2 --assert -DFORMAL "
            f"--top-module {TOP} {TOP}.sv dut.sv props_locked.sv"
        )
        code, output = _docker_run(
            work,
            build,
            image=image,
            docker=docker,
            timeout=build_timeout,
            name=f"bendeda-tf-build-{uuid4().hex[:8]}",
        )
        if code != 0:
            raise RuntimeError(f"verilator did not build the bench (rc {code}): {_tail(output)}")

        verdicts: list[TraceVerdict] = []
        for index in range(len(traces)):
            code, output = _docker_run(
                work,
                f"./obj_dir/V{TOP} +trace={index} +cycles={cycles}",
                image=image,
                docker=docker,
                timeout=run_timeout,
                name=f"bendeda-tf-trace-{uuid4().hex[:8]}",
            )
            match = ASSERTION.search(output)
            if match:
                message = next(
                    (line.strip() for line in output.splitlines() if "Assertion failed" in line),
                    output.strip()[:400],
                )
                source = SOURCE_LINE.search(message)
                observed = _last_cycle(work / "cycle.txt")
                verdicts.append(
                    TraceVerdict(
                        trace=index,
                        cycles=cycles,
                        failure=Failure(
                            assertion=match.group(1),
                            # The pack judges a transition one edge after it happens;
                            # the trace cycle is the iteration before the report.
                            cycle=observed - 1 if observed is not None and observed > 0 else None,
                            observed_at=observed,
                            line=int(source.group(1)) if source else None,
                            message=message,
                        ),
                    )
                )
            elif code != 0:
                raise RuntimeError(
                    f"trace {index}: the bench failed without an assertion (rc {code}): {_tail(output)}"
                )
            else:
                verdicts.append(TraceVerdict(trace=index, cycles=cycles, failure=None))

    return BenchReport(
        image=image, image_id=_image_id(docker, image), declared=declared, verdicts=verdicts
    )
