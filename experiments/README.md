# Experiments

One file per run matrix. `bendeda run --matrix <file> [--dry-run] [--limit N]` expands
the cells deterministically, runs each one in the sandbox, re-executes the declared gates
and writes a bundle `score` can read. The schema per run is
`bendeda/schemas/run.schema.json`; the matrix itself is validated by
`bendeda/matrix.py`, which names the offending field rather than accepting a half-specified
matrix.

## Smoke matrix

`matrices/smoke.json` is one cell: `toy_counter`, arm `C0`, seed 1, the `trace` gate, and
a policy (`matrices/smoke.policy.json`) that permits workspace reads and `submit`. It
exists to prove the wiring end to end, not to produce a result:

```bash
bendeda run --matrix experiments/matrices/smoke.json --dry-run
bendeda run --matrix experiments/matrices/smoke.json --limit 1
```

A cell is reported `complete` only when `score` says every verdict exists. `O` has no
source here — the oracle pack is scored on the scoring host — so a smoke cell exits 3
with `S` and `V` present and `O` absent. The result comes back through:

```bash
bendeda oracle score --pack path/to/oracle/pack \
  --commitment oracle_sealed/commitment.json \
  --bundle .bend-cache/runs/smoke/C0-toy_counter-s1 --host scoring-1
```

`oracle score` refuses a pack that no longer matches the commitment, runs the pack's own
`score.py` (called as `score.py <bundle>`, printing `{"components": {...}}`), and records
the result. A host that scores the bundle by other means still has `oracle record`:

```bash
bendeda oracle record --bundle .bend-cache/runs/smoke/C0-toy_counter-s1 \
  --components components.json --host scoring-1 \
  --commitment oracle_sealed/commitment.json
```

`experiments/fixtures/demo_pack/` is a stand-in pack, committed in the clear with a
`commitment.json` beside it, so the scoring half can be tried on a real cell:

```bash
bendeda oracle score --pack experiments/fixtures/demo_pack \
  --commitment experiments/fixtures/demo_pack.commitment.json \
  --bundle .bend-cache/runs/smoke/C0-toy_counter-s1 --host demo-pack
```

It is not the oracle — the real pack stays outside the repository — and
`tests/test_oracle.py` fails if the pack and its commitment drift apart.

`components.json` maps each pack component to a boolean. Both commands write
`oracle.json` with the host and the pack's Merkle root, which is what lets `score`
compute `O` without trusting a number someone typed in prose. A pack may also publish a
`VERSION` file; it is a component like any other, so the commitment covers it, and the
label is recorded beside the root. `score` echoes all of that in an `oracle` block, so an
`O` names the pack that produced it. They refuse a void bundle, a
bundle that already scored `S=0` (zero is already the answer), and a bundle that already
carries a result: a second score is a disagreement, not an update.

`matrices/budget.json` is the same cell with a one-call allowance and a command that
tries three calls. It exists to show the enforcement, not the classification: the cell
records `budget_exhausted: true`, the sandbox is stopped, and the log scores `S=V=O=0`.
That cell exits 0, because a spent allowance is a result rather than an incomplete run.
`oracle score` refuses such a bundle too — `S=0` already fixes `O=0` — so the zero is
`score`'s, not a pack's.

```json
{
  "name": "smoke",
  "image": "bendeda/harness:0.0.1",
  "sim_image": "bendeda/oss-cad:2026-11-20",
  "network": "bendeda-offline",
  "policy": "experiments/matrices/smoke.policy.json",
  "command": ["python", "-m", "bendeda", "--version"],
  "budgets": { "tool_calls": 40 },
  "visible_gates": ["trace"],
  "tasks": [{ "name": "toy_counter", "artifacts": "experiments/fixtures/toy_counter" }],
  "arms": ["C0"],
  "seeds": [1]
}
```

`image` is what the agent runs in; `sim_image` is what the gates simulate in. Passing one
for both made the trace gate report a fail, because the harness image has no Verilator.

## Corpus

Four gate-calibration corpora (LA4). Each is one or more bases plus one- or two-file
variants — three correct implementations, three mutants and three to five seeded
defects — so a bug reads as a diff rather than a second copy of the task.

| Corpus | Bases | Gates | What it measures |
|---|---|---|---|
| `corpus/toy_counter/` | `fixtures/toy_counter` | `trace` | model and RTL agree on a submitted artifact directory |
| `corpus/b1_fifo_laws/` | `tasks/seq/B1_fifo` | `lint` | a law package passes rules L001-L015 |
| `corpus/toy_counter_laws/` | `fixtures/toy_counter_laws` | `trace`, `formal`, `lint` | one submission judged by all three gates |
| `corpus/b1_fifo_rtl/` | `tasks/seq/B1_fifo` + `submission` | `lint`, `formal` | a study task's laws and a submitted RTL, staged from two bases |

```bash
bendeda gate calibrate --corpus experiments/corpus/toy_counter --out .bend-cache/calibrate.json
bendeda gate calibrate --corpus experiments/corpus/b1_fifo_laws
bendeda gate calibrate --corpus experiments/corpus/toy_counter_laws --sim-timeout 600
bendeda gate calibrate --corpus experiments/corpus/b1_fifo_rtl
```

The output says what each gate decided, not only what the set did: `per gate:` lists the
bugs a gate caught, how many it caught alone, and how many correct implementations it
rejected, and the summary names any gate that caught nothing.

The third corpus exists because the first two exercise one gate each, and `per gate:`
is only worth reading when the gates answer on the same entries. Its base is the one
fixture that carries RTL, an SVA pack and a law package together, so a mutant can fail
`trace`, a design that is right inside the simulated window can fail `formal`, and a
seeded defect can fail `lint` on the same corpus; the contribution table then shows
each gate earning its place. The `formal` entry is the one the plan cannot reach: every
value in `plan.json` is 4 or less, and `props.sv` asks for an increment of 8.
`--sim-timeout` bounds a hung simulation: an entry whose DUT never returns is a
rejected entry with that reason, not a calibration that runs until someone notices.

The fourth corpus is the study-task shape: `corpus.json` names the B1 package and a
`submission/` directory as two bases, staged in order, so `rtl/*.sv` stays the agent's
(§4.1) while the laws, model and locked SVA pack stay the task's. It calibrates at
GS 1.000 and GSp 1.000 over `lint` and `formal`, each gate catching its three entries
and nothing else.

All four are fixture-scale. A study task's corpus adds the MCY mutant set for that
task. What `b1_fifo_rtl` cannot yet show is `trace`: the L1 vector driver speaks only
`step(U32, U32)`, and `tasks/seq/B1_fifo`'s `step(Fifo, Op)` has no driver, so the
corpus names `lint` and `formal`. The missing piece is a driver for an algebraic
input, not a staging problem.

## Planned matrices

| File | Phase | Matrix |
|---|---|---|
| `pilot.yaml` | 3 | 4 tasks x 2 models x 3 seeds x all arms; calibrates budgets and variance |
| `trackA.yaml` | 4 | 12 tasks x 5 arms x 3 models x 10 seeds = 1,800 runs |
| `ablations.yaml` | 4 | A1-A7 on a 4-task subset |
| `trackB.yaml` | 5 | 20 tool-action scenarios x 4 gating arms |
| `trackC.yaml` | 5 | 4 PCB tasks x 4 arms (exploratory) |
| `trackD.yaml` | 5 | 40 lemmas x 3 languages |

## Order, and the prereg hash

A matrix may declare how its cells are ordered:

```json
"order": { "method": "hash-v1", "seed": 7 }
```

`declared` (the default) is task-major, then arm, then seed. `hash-v1` sorts each cell
label by `sha256("<seed>:<label>")`: reproducible on any machine and Python version
because there is no RNG state to reproduce, and it interleaves arms so a slow service
does not become an arm effect. `bendeda run` prints the prereg hash and writes
`prereg.json` beside the bundles with the order that was actually executed and the
labels in it.

The hash covers every declared field with the defaults folded in, so editing a default
in `matrix.py` changes every prereg. That is the point: a run whose meaning moved under
it is not the run that was frozen.

## Rules

- Cells are ordered by an explicit seed (`order`) rather than by declaration order once
  a matrix is frozen, and arms are interleaved, so a slow service does not become an
  arm effect.
- Budgets are recorded per run, and the L0/RTL split from Appendix K (G-04) is
  explicit rather than implied.
- An experiment file is frozen at `prereg-v1`; changes after that are amendments.
- The full matrix never runs in CI. It runs on the study host and publishes bundles
  as release assets with a `SHA256SUMS` file.
