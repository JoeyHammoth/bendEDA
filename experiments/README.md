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
with `S` and `V` present and `O` absent.

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

## Planned matrices

| File | Phase | Matrix |
|---|---|---|
| `pilot.yaml` | 3 | 4 tasks x 2 models x 3 seeds x all arms; calibrates budgets and variance |
| `trackA.yaml` | 4 | 12 tasks x 5 arms x 3 models x 10 seeds = 1,800 runs |
| `ablations.yaml` | 4 | A1-A7 on a 4-task subset |
| `trackB.yaml` | 5 | 20 tool-action scenarios x 4 gating arms |
| `trackC.yaml` | 5 | 4 PCB tasks x 4 arms (exploratory) |
| `trackD.yaml` | 5 | 40 lemmas x 3 languages |

## Rules

- Run order is randomised with a logged seed and arms are interleaved, so a slow
  service does not become an arm effect.
- Budgets are recorded per run, and the L0/RTL split from Appendix K (G-04) is
  explicit rather than implied.
- An experiment file is frozen at `prereg-v1`; changes after that are amendments.
- The full matrix never runs in CI. It runs on the study host and publishes bundles
  as release assets with a `SHA256SUMS` file.
