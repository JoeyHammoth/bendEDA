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

## What it deliberately does not prove

- Nothing about RTL correctness: the DUT used in the self-test is a Python
  cycle-accurate stub, standing in for the cocotb adapter that arrives with the
  EDA image. The path is proved; the simulator is not.
- Nothing about laws: no `LAWS.bend`, no `PROOF.bend`, no conformance ladder above
  L1. Those are issues #8 and #14.
