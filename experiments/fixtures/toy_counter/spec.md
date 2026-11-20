# Toy counter — vector-path fixture

**Status:** fixture, not a task. It has no laws, no oracle and no arm; it exists so
that issue #7 ("prove the `model.mjs` vector path end to end") is closed by a
running pipeline rather than by a plan.

## Contract

A 4-bit saturating counter.

| Element | Requirement |
|---|---|
| `step(count, inc)` | `min(count + inc, 15)` for `count ≤ 15` |
| `run(xs, count)` | `step` folded over `xs` |
| Saturation | at 15 the counter stays at 15, it does not wrap |
| Domain | `count ∈ [0, 15]`, `inc ∈ [0, 15]` |

## What the path proves

1. `bend model.bend -o model.mjs` emits an importable ES module at the pinned
   compiler commit.
2. A Node driver (`tools/model_vectors.mjs`) calls the exported defs with a
   deterministic stimulus plan and emits `vectors.json`.
3. The comparator (`bendeda conformance trace`) diffs model output against a DUT
   and **detects a one-cycle offset**, which is the acceptance criterion that
   separates "it ran" from "it checks".
4. The same comparator judges **real RTL**: `--dut verilator --rtl dut.sv` runs
   `dut.sv` under Verilator in the pinned OSS CAD image and compares its samples
   with the model's. `dut_wrap.sv` is the negative control — RTL that wraps at
   16 instead of saturating — and the gate must reject it as a *value* mismatch,
   not as an offset.

## What it deliberately does not prove

- Nothing about generality: the testbench is written for this fixture's port
  list, so a new task needs its own harness. A generic RTL runner is Phase 2.
- Nothing about the DUT's timing beyond one sample per clock; CDC, reset
  sequencing and multi-clock behaviour are outside L1.
- Nothing about laws: no `LAWS.bend`, no `PROOF.bend`, no conformance ladder above
  L1. Those are issues #8 and #14.
