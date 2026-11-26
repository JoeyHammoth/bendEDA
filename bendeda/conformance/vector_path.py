# SPDX-License-Identifier: Apache-2.0
"""The L1 vector path, executable half (design document §4.2, Appendix K G-03).

Three steps, each testable on its own:

1. `compile_model` — `bend model.bend -o model.mjs`, at a pinned compiler commit.
2. `run_vectors`   — drive the emitted ES module from Node with a stimulus plan.
3. `compare`       — diff model output against a DUT and, when it differs, say
                     *how*: a one-cycle offset is a different defect from a wrong
                     value, and conflating them is how trace conformance turns
                     into a shrug.

The DUT comes in two kinds. `stub` is a Python cycle-accurate reference, used by
the unit tests and by a machine with no simulator. `verilator` compiles real RTL
in the pinned OSS CAD image and returns the samples it produced, so the
comparator judges silicon-shaped behaviour instead of a second copy of the model.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

DEFAULT_DRIVER = Path("tools/model_vectors.mjs")
DEFAULT_SPEC = Path("experiments/fixtures/toy_counter/dut.json")
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
DEFAULT_IMAGE = "bendeda/oss-cad:2026-11-20"
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


def write_stimulus(path: Path, values: list[int], width: int) -> None:
    """Write stimulus as hex words of `width` bits, one per line, for `$readmemh`."""
    digits = (width + 3) // 4
    path.write_text("".join(f"{value:0{digits}x}\n" for value in values), encoding="utf-8")


def parse_trace(path: Path) -> list[int]:
    """Read a single decimal sample per line, ignoring blanks and `#` comments."""
    values: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        values.append(int(line, 10))
    return values


def parse_trace_table(path: Path, columns: int) -> list[list[int]]:
    """Read one row of `columns` decimal samples per line."""
    rows: list[list[int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != columns:
            raise ValueError(f"expected {columns} sample(s) per line, got {len(parts)}: {line!r}")
        rows.append([int(part, 10) for part in parts])
    return rows


def load_spec(spec) -> dict:
    """Read a port manifest from a path, or accept a mapping as-is."""
    if isinstance(spec, dict):
        return spec
    return json.loads(Path(spec).read_text(encoding="utf-8"))


def _port_name(value, where: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.match(value):
        raise ValueError(f"{where}: {value!r} is not a port identifier")
    return value


def _width(value, where: str) -> int:
    width = int(value)
    if not 1 <= width <= 4096:
        raise ValueError(f"{where}: width must be 1..4096, got {width}")
    return width


def validate_spec(spec) -> dict:
    """Return a normalised port manifest, or raise ValueError naming the problem.

    The manifest is deliberately small: one clock, optional reset and enable, any
    number of inputs and outputs. A task that needs more than this needs a real
    harness; stretching this generator past what it can express would produce
    benches that are wrong in ways nobody notices.
    """
    spec = load_spec(spec)
    if not isinstance(spec, dict):
        raise ValueError("spec must be a JSON object")

    top = _port_name(spec.get("top", ""), "top")
    clock = spec.get("clock") or {}
    if not isinstance(clock, dict):
        raise ValueError("clock must be an object")
    clock_port = _port_name(clock.get("port", ""), "clock.port")
    period = int(clock.get("period_ns", 10))
    if period < 2:
        raise ValueError("clock.period_ns must be at least 2")
    used = {clock_port}

    def optional(key: str) -> dict | None:
        entry = spec.get(key)
        if entry is None:
            return None
        if not isinstance(entry, dict):
            raise ValueError(f"{key} must be an object")
        port = _port_name(entry.get("port", ""), f"{key}.port")
        if port in used:
            raise ValueError(f"port {port!r} appears twice")
        used.add(port)
        return {"port": port, **{k: v for k, v in entry.items() if k != "port"}}

    reset = optional("reset")
    enable = optional("enable")

    inputs: list[dict] = []
    for index, entry in enumerate(spec.get("inputs", [])):
        if not isinstance(entry, dict):
            raise ValueError(f"inputs[{index}] must be an object")
        port = _port_name(entry.get("port", ""), f"inputs[{index}].port")
        if port in used:
            raise ValueError(f"port {port!r} appears twice")
        used.add(port)
        stimulus = entry.get("stimulus", "const")
        if stimulus not in ("plan", "incs", "const"):
            raise ValueError(f"{port}: stimulus must be 'plan', 'incs' or 'const'")
        inputs.append({
            "port": port,
            "width": _width(entry.get("width", 1), port),
            "stimulus": stimulus,
            "key": str(entry.get("key", port)),
            "value": int(entry.get("value", 0)),
        })

    if not inputs:
        raise ValueError("spec needs at least one input; there is nothing to drive")

    outputs: list[dict] = []
    for index, entry in enumerate(spec.get("outputs", [])):
        if not isinstance(entry, dict):
            raise ValueError(f"outputs[{index}] must be an object")
        port = _port_name(entry.get("port", ""), f"outputs[{index}].port")
        if port in used:
            raise ValueError(f"port {port!r} appears twice")
        used.add(port)
        outputs.append({"port": port, "width": _width(entry.get("width", 1), port)})
    if not outputs:
        raise ValueError("spec needs at least one output")

    compare = spec.get("compare", outputs[0]["port"])
    if compare not in {item["port"] for item in outputs}:
        raise ValueError(f"compare {compare!r} is not one of the outputs")

    return {
        "top": top,
        "clock": {"port": clock_port, "period_ns": period},
        "reset": reset,
        "enable": enable,
        "inputs": inputs,
        "outputs": outputs,
        "compare": compare,
    }


def _declaration(kind: str, name: str, width: int, initial: str | None) -> str:
    text = f"{kind} {name}" if width == 1 else f"{kind} [{width - 1}:0] {name}"
    if initial is not None:
        text += f" = {initial}"
    return text + ";"


def render_testbench(spec) -> str:
    """Generate a Verilator testbench from a port manifest.

    The generated bench is written into a temporary directory and discarded: the
    manifest is the source of truth, so a new task supplies a manifest instead of
    a hand-written testbench. Generation is deterministic, which is what makes it
    reviewable in tests rather than by eye.
    """
    spec = validate_spec(spec)
    clock = spec["clock"]
    reset = spec["reset"]
    enable = spec["enable"]
    inputs = spec["inputs"]
    outputs = spec["outputs"]
    half = max(1, clock["period_ns"] // 2)
    width = sum(item["width"] for item in inputs)

    lines = [
        "// SPDX-License-Identifier: Apache-2.0",
        "// Generated from a port manifest by `bendeda conformance trace`. Do not edit;",
        "// change the manifest instead.",
        "`timescale 1ns/1ps",
        "`default_nettype none",
        "module tb_dut;",
        f"  reg {clock['port']} = 1'b0;",
    ]
    if reset:
        initial = 1 if reset.get("active_high", True) else 0
        lines.append(f"  reg {reset['port']} = 1'b{initial};")
    if enable:
        initial = 1 if enable.get("active_high", True) else 0
        lines.append(f"  reg {enable['port']} = 1'b{initial};")
    for item in inputs:
        lines.append("  " + _declaration("reg", item["port"], item["width"], f"{item['width']}'d0"))
    for item in outputs:
        lines.append("  " + _declaration("wire", item["port"], item["width"], None))
    lines += [
        f"  reg [{width - 1}:0] row;",
        f"  reg [{width - 1}:0] stim [0:1023];",
        "  integer cycles;",
        "  integer i;",
        "  integer fd;",
        "",
        f"  {spec['top']} dut (",
    ]
    connections = [f"    .{clock['port']}({clock['port']})"]
    if reset:
        connections.append(f"    .{reset['port']}({reset['port']})")
    if enable:
        connections.append(f"    .{enable['port']}({enable['port']})")
    for item in inputs + outputs:
        connections.append(f"    .{item['port']}({item['port']})")
    lines.append(",\n".join(connections))
    lines += [
        "  );",
        "",
        f"  always #{half} {clock['port']} = ~{clock['port']};",
        "",
        "  initial begin",
        '    if (!$value$plusargs("cycles=%d", cycles))',
        "      cycles = 16;",
        '    $readmemh("stim.hex", stim);',
        '    fd = $fopen("dut_trace.txt", "w");',
        "    if (fd == 0) begin",
        '      $display("tb_dut: cannot open dut_trace.txt");',
        "      $finish;",
        "    end",
    ]
    if reset:
        lines += [
            f"    repeat ({int(reset.get('cycles', 1))}) @(posedge {clock['port']});",
            f"    #1 {reset['port']} = 1'b{0 if reset.get('active_high', True) else 1};",
        ]
    lines += ["    for (i = 0; i < cycles; i = i + 1) begin", "      row = stim[i];"]
    offset = 0
    for item in inputs:
        lines.append(f"      {item['port']} = row[{offset} +: {item['width']}];")
        offset += item["width"]
    lines += [f"      @(posedge {clock['port']});", "      #1;"]
    fmt = " ".join(["%0d"] * len(outputs))
    args = ", ".join(item["port"] for item in outputs)
    lines += [f'      $fdisplay(fd, "{fmt}", {args});', "    end", "    $fclose(fd);", "    $finish;", "  end", "endmodule", "`default_nettype wire", ""]
    return "\n".join(lines)


def load_plan(plan) -> dict:
    """Read a stimulus plan from a path, or accept a mapping as-is."""
    if isinstance(plan, dict):
        return validate_plan(plan)
    return validate_plan(json.loads(Path(plan).read_text(encoding="utf-8")))


def validate_plan(plan) -> dict:
    """Check a stimulus plan and return it with `stimulus` normalised.

    `incs` stays because it is the model's stimulus: the driver walks it one
    entry per cycle. `stimulus` maps an input name to its own sequence, which is
    how a design with two or three inputs is driven without inventing a second
    plan format.
    """
    if not isinstance(plan, dict):
        raise ValueError("plan must be a JSON object")
    incs = plan.get("incs")
    if not isinstance(incs, list) or not incs:
        raise ValueError("plan.incs must be a non-empty list")
    if not all(isinstance(value, int) and value >= 0 for value in incs):
        raise ValueError("plan.incs values must be non-negative integers")
    stimulus = plan.get("stimulus") or {}
    if not isinstance(stimulus, dict):
        raise ValueError("plan.stimulus must be an object of name -> sequence")
    for key, values in stimulus.items():
        if not isinstance(values, list):
            raise ValueError(f"plan.stimulus.{key} must be a list")
        if len(values) < len(incs):
            raise ValueError(
                f"plan.stimulus.{key} has {len(values)} values for {len(incs)} cycles"
            )
    count0 = plan.get("count0", 0)
    if not isinstance(count0, int) or count0 < 0:
        raise ValueError("plan.count0 must be a non-negative integer")
    entries = plan.get("entries", ["step", "run"])
    if not isinstance(entries, list) or not entries:
        raise ValueError("plan.entries must be a non-empty list")
    return {**plan, "count0": count0, "entries": entries, "stimulus": stimulus}


def build_stimulus(spec, plan) -> tuple[list[int], int]:
    """Pack one stimulus word per cycle, in manifest order, least-significant first.

    Each input takes its values independently: a constant, the model's `incs`, or
    its own sequence from `plan.stimulus`. That last case is the point — an
    enable that deasserts mid-run cannot be expressed as a single shared list.
    """
    spec = validate_spec(spec)
    plan = validate_plan(plan)
    cycles = len(plan["incs"])
    width = sum(item["width"] for item in spec["inputs"])
    words: list[int] = []
    for index in range(cycles):
        word = 0
        offset = 0
        for item in spec["inputs"]:
            if item["stimulus"] == "const":
                value = item["value"]
            elif item["stimulus"] == "incs":
                value = plan["incs"][index]
            else:
                if item["key"] not in plan["stimulus"]:
                    raise ValueError(
                        f"input {item['port']!r} wants plan.stimulus.{item['key']}, which the plan does not define"
                    )
                value = plan["stimulus"][item["key"]][index]
            word |= (int(value) & ((1 << item["width"]) - 1)) << offset
            offset += item["width"]
        words.append(word)
    return words, width


def shift_trace(trace: list[int], offset: int) -> list[int]:
    """Move a DUT trace later by `offset` cycles, keeping its length.

    This is the negative control applied to whichever DUT ran, stub or
    simulator: a comparator that cannot see a one-cycle shift is not checking
    anything, and the shift is easier to inject here than in RTL.
    """
    if offset <= 0 or not trace:
        return list(trace)
    return [trace[0]] * offset + trace[: max(0, len(trace) - offset)]


def image_available(image: str = DEFAULT_IMAGE, docker: str = "docker") -> bool:
    """True only when the simulator image is already present locally.

    Checked rather than assumed: a host can have Docker installed and still not
    have the image, and `docker run` would then try to pull a name that is not in
    any registry. A test must skip with that reason, not fail as if the DUT were
    broken.
    """
    try:
        done = subprocess.run(
            [docker, "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def verilator_command(
    workdir: Path,
    cycles: int,
    image: str = DEFAULT_IMAGE,
    docker: str = "docker",
    name: str | None = None,
) -> list[str]:
    """Build the container command that compiles and runs the testbench.

    Verilator's `--binary` mode needs a C++ compiler and make, which is why the
    image carries them; the compile happens inside the container so the host
    needs no toolchain at all.
    """
    inner = (
        "verilator --binary --timing -Wno-fatal -j 2 --top-module tb_dut "
        f"tb_dut.sv dut.sv && ./obj_dir/Vtb_dut +cycles={cycles}"
    )
    command = [docker, "run", "--rm"]
    if name:
        # A name is what makes a hung simulation killable: `subprocess` can stop the
        # client, and only the daemon can stop the process the client started.
        command += ["--name", name]
    command += ["-v", f"{workdir}:/work", "-w", "/work"]
    if hasattr(os, "getuid"):
        command += ["-u", f"{os.getuid()}:{os.getgid()}"]
    # `bash -c`, never `bash -lc`: a login shell sources /etc/profile, which
    # rewrites PATH and loses the image's /opt/oss-cad-suite/bin. The failure is
    # `verilator: command not found` even though the image ships it.
    return command + [image, "bash", "-c", inner]


def _remove_container(docker: str, name: str, remove=None) -> None:
    """Best effort: the container may already be gone, and that is the good case."""
    remove = remove or subprocess.run
    try:
        remove([docker, "rm", "-f", name], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        pass


def simulate_verilator(
    rtl: Path,
    spec,
    plan,
    image: str = DEFAULT_IMAGE,
    docker: str = "docker",
    timeout: int = 900,
    *,
    runner=None,
    remove=None,
) -> list[int]:
    """Run `rtl` against a generated testbench and return the compared output.

    `spec` is a port manifest and `plan` a stimulus plan (path or mapping). Both
    can describe several inputs, so a new task supplies data rather than code.
    """
    if not rtl.exists():
        raise FileNotFoundError(f"no RTL at {rtl}")
    plan = validate_plan(plan)
    cycles = len(plan["incs"])
    manifest = validate_spec(spec)
    values, width = build_stimulus(manifest, plan)

    with tempfile.TemporaryDirectory(prefix="bendeda-dut-") as raw:
        workdir = Path(raw)
        shutil.copyfile(rtl, workdir / "dut.sv")
        (workdir / "tb_dut.sv").write_text(render_testbench(manifest), encoding="utf-8")
        write_stimulus(workdir / "stim.hex", values, width)
        name = f"bendeda-dut-{uuid4().hex[:8]}"
        try:
            done = (runner or subprocess.run)(
                verilator_command(workdir, cycles, image=image, docker=docker, name=name),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            # The client is killed by `subprocess`; the daemon's process is not, and it
            # would keep the temporary directory busy forever. One hung simulation must
            # not hold a calibration entry for longer than its timeout.
            _remove_container(docker, name, remove)
            raise RuntimeError(
                f"the simulation did not finish within {timeout}s; "
                f"its container {name} was removed"
            ) from exc
        except OSError as exc:
            _remove_container(docker, name, remove)
            raise RuntimeError(f"cannot run {docker!r}: {exc}") from exc
        if done.returncode != 0:
            detail = (done.stderr or done.stdout).strip()
            raise RuntimeError(f"verilator failed ({done.returncode}): {detail[:1500]}")
        trace_path = workdir / "dut_trace.txt"
        if not trace_path.exists():
            raise RuntimeError("verilator ran but produced no dut_trace.txt")
        table = parse_trace_table(trace_path, len(manifest["outputs"]))

    if len(table) != cycles:
        raise RuntimeError(f"the DUT produced {len(table)} samples for {cycles} cycles")
    index = [item["port"] for item in manifest["outputs"]].index(manifest["compare"])
    return [row[index] for row in table]


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
    dut_trace: list[int] | None = None,
) -> Comparison:
    """Diff model cycle outputs against the DUT.

    `dut_trace` supplies samples from a real simulation; without it the Python
    reference computes them. `inject_offset` shifts whichever trace was used,
    which is how the acceptance criterion "detects an injected one-cycle offset"
    is checked against a simulator as well as against the stub.
    """
    model_steps: list[int] = [int(step["out"]) for step in steps]

    if dut_trace is not None:
        dut_steps = list(dut_trace)
    else:
        dut_steps = []
        count = count0
        for step in steps:
            count = dut(count, int(step["inc"]))
            dut_steps.append(count)
    if inject_offset:
        dut_steps = shift_trace(dut_steps, inject_offset)

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
    """A plan that exercises saturation and also names the fixture's input.

    `stimulus.inc` is redundant with `incs` for this fixture; it is here so the
    default path exercises the per-input plan support that a multi-input design
    needs, instead of leaving it to the tests alone.
    """
    incs = [1, 2, 3, 1, 4, 2, 1, 3]
    incs = (incs * ((cycles // len(incs)) + 1))[:cycles]
    return {
        "count0": 0,
        "cycles": cycles,
        "incs": incs,
        "stimulus": {"inc": list(incs)},
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
    try:
        plan = load_plan(args.plan) if args.plan else default_plan(args.cycles)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"conformance trace: bad plan: {exc}", file=sys.stderr)
        return 2
    try:
        payload = run_vectors(module, plan, driver=Path(args.driver), node=args.node)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"conformance trace: {exc}", file=sys.stderr)
        return 1

    dut_trace = None
    if args.dut == "verilator":
        if not args.rtl:
            print("conformance trace: --dut verilator needs --rtl", file=sys.stderr)
            return 2
        try:
            dut_trace = simulate_verilator(
                Path(args.rtl),
                Path(args.spec),
                plan,
                image=args.image,
                docker=args.docker,
                timeout=args.sim_timeout,
            )
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            print(f"conformance trace: {exc}", file=sys.stderr)
            return 1

    comparison = compare(
        payload["steps"],
        count0=plan["count0"],
        inject_offset=args.inject_offset,
        dut_trace=dut_trace,
    )
    report = {
        "module": str(module),
        "cycles": comparison.total,
        "matches": comparison.matches,
        "detected_offset": comparison.detected_offset,
        "first_divergence": comparison.first_divergence,
        "mismatches": len(comparison.mismatches),
        "injected_offset": args.inject_offset,
        "dut": args.dut,
        "rtl": args.rtl,
        "spec": args.spec,
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
        print(f"dut      : {args.dut}{' (' + str(args.rtl) + ')' if args.rtl else ''}")
        if args.dut == "verilator":
            print(f"spec     : {args.spec}")
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
