# Experiments

One YAML file per run matrix, validated against `bendeda/schemas/run.schema.json`.
Nothing here executes yet: `bendeda run <file>` is a declared stub that exits
non-zero (Phase 2).

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
