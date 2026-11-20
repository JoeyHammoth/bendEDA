# Results

Small, diff-friendly aggregates live here (CSV/JSON tables, the report's numbers).
Raw run artifacts do **not**: `events.jsonl`, gate outputs and per-run bundles are
large, and they belong in release assets with a `SHA256SUMS` manifest, archived as
a citable snapshot at release.

## Rules

- A number in this directory must be reproducible from a named bundle and a named
  analysis script at a named commit. If it is not, it does not go here.
- Negative and null results are published with the same prominence as positive
  ones; a results file that only contains favourable numbers is a red flag.
- `results/runs/` is ignored by git on purpose (`replay` reads bundles, not
  in-tree dumps).
- Every table carries the protocol tag it was produced under (`prereg-v1` and
  later). Post-freeze exploratory analysis is prefixed `exploratory-`.
