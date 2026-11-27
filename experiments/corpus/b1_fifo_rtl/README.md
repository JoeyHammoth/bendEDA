# b1_fifo_rtl corpus — a task package and a submitted RTL, judged together (LA4)

The other corpora stage one base: a fixture that carries the model, the RTL and the
laws. A study task cannot ship that base. The design gives `rtl/*.sv` to the agent
(§4.1), so the implementation has to come from a submission, while the laws, the
model, the abstraction map and the locked SVA pack come from the task package.

This corpus is the first with two bases:

```json
"bases": ["../../../tasks/seq/B1_fifo", "submission"]
```

`load_corpus` stages them in order and then the entry, so `as_shipped` is the B1
package with nothing replaced and `dut.sv` is supplied by the submission. The old
one-base spelling still loads, and `Corpus.bases` is the ordered tuple.

| Kind | What it is | Count |
|---|---|---|
| `correct` | FIFOs the task accepts: a count-and-table design, a shift register, two presence flags | 3 |
| `mutant` | one small edit to the reference RTL, all in the transition table | 3 |
| `seeded` | the law-package defects the `b1_fifo_laws` corpus seeds, on the same task | 3 |

`corpus.json` names both bases, the gate set (`["lint", "formal"]`) and the entries.
The gates split the corpus between them: a mutant changes only `dut.sv`, which
`lint` does not read, and a seeded defect changes only `laws.manifest.yaml`, which
the `.sby` job does not read.

## Measured

Each entry was staged with `bendeda.gates.stage` in a directory of its own; `lint`
was run through `lint_gate`, and `formal` by running the task's own
`props_locked.sby` (`smtbmc z3`, BMC depth 12) on the staged files with SymbiYosys.
The container path was not used — Docker was not running — so these are the same
files and the same job, not the same gate.

| Entry | Kind | `lint` | `formal` | What decided it |
|---|---|---|---|---|
| `as_shipped` | correct | pass | pass | — |
| `shift_register` | correct | pass | pass | — |
| `presence_flags` | correct | pass | pass | — |
| `m01_pop_keeps_count` | mutant | pass | fail | `p_pop_full_count` |
| `m02_pushpop_full_push_wins` | mutant | pass | fail | `p_pushpop_full_count` |
| `m03_pushpop_half_wrong_head` | mutant | pass | fail | `p_pushpop_half_head` |
| `s01_ghost_law` | seeded | fail | pass | L002 |
| `s02_untraceable` | seeded | fail | pass | L003 |
| `s03_stale_hash` | seeded | fail | pass | L014 |

Three of the three seeded defects fail only `lint`, and three of the three mutants
fail only `formal`; every correct implementation passes both. The first run of
`presence_flags` failed `p_count_within_depth` and `p_full_iff_depth`, and it was the
RTL that was wrong: the occupancy was the two flags concatenated, so full read as 3
rather than 2. The pack caught a real defect in an implementation written to be
correct, which is the reason to keep the corrected one as an entry rather than to
quietly fix it.

GS and GSp are **not** reported as calibration results. `gate calibrate` needs the
OSS CAD image and Docker is not running on this host (the Linux engine pipe is
absent), so the numbers a calibration would print were not measured: this table
alone would imply GS 1.000 (mutant 3/3, seeded 3/3) and GSp 1.000 (3/3 correct), and
that implication is local evidence, not a `calibrate` run.

## What this does not cover

- **`trace`.** The L1 vector driver speaks `step(U32, U32)`, and B1's model is
  `step(Fifo, Op)`, so a FIFO cannot be driven by the plan's input vectors. This
  corpus names `lint` and `formal` only; a trace gate for an algebraic input is open
  work, not a gate that was dropped for convenience.
- **Deep proofs.** `props_locked.sby` is BMC at depth 12. A correct implementation is
  accepted only to that depth; the mutants fail inside it.
- **A scored submission.** The submission here is a reference the corpus author wrote
  to exercise the pipeline. It is not a study-run artifact, and the two gates being
  calibrated on it says nothing about a model's submission.
- **The seeded entries' `formal` pass.** The three seeded defects are law-metadata
  defects; the `.sby` job reads none of the files they break. Their passing `formal`
  is expected, and a corpus cannot use it as evidence that the formal gate is weak.
