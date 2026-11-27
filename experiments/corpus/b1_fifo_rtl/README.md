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

`corpus.json` names both bases, the gate set (`["trace", "lint", "formal"]`) and the
entries. A mutant changes only `dut.sv`, which `lint` does not read; a seeded defect
changes only `laws.manifest.yaml`, which neither behavioural gate reads.

The submission also carries `dut.json` (the port manifest the generated testbench is
built from) and `plan.json`, which drives the FIFO with one model constructor per
cycle:

```json
{
  "ops": [{"op": "Push", "din": 11}, {"op": "Pop"}],
  "init": "empty_fifo",
  "observe": "dout",
  "stimulus": {"push": [1, 0], "pop": [0, 1], "din": [11, 0]}
}
```

That is the algebraic counterpart of the counter's `incs` plan: the driver builds each
`Op` from the model's own constructor, threads the opaque state through `step`, and
records `dout` after every cycle. The plan includes a push/pop pair on a **full** queue,
which is the case the first plan missed: without it, `m02` survived `trace` while its
occupancy was already wrong.

## Measured

`bendeda gate calibrate` ran on this corpus with Docker up, the OSS CAD image present,
and the pinned Bun and compiler exported:

```console
$ export BENDEDA_BUN=.bend-cache/bunenv/node_modules/.bin/bun
$ export BENDEDA_BEND_CLI=.bend-cache/bend-2.0.40/bend2/main.ts
$ python -m bendeda gate calibrate --corpus experiments/corpus/b1_fifo_rtl
...
  per gate:
    trace      caught 3 bug(s), 0 of them alone; rejected 0 correct implementation(s)
    lint       caught 3 bug(s), 3 of them alone; rejected 0 correct implementation(s)
    formal     caught 3 bug(s), 0 of them alone; rejected 0 correct implementation(s)
gate calibrate: GS 1.000 (mutant 1.000 3/3, seeded 1.000 3/3), GSp 1.000 (3/3 correct)
$ echo $?
0
```

| Entry | Kind | `trace` | `lint` | `formal` | What decided it |
|---|---|---|---|---|---|
| `as_shipped` | correct | pass | pass | pass | — |
| `shift_register` | correct | pass | pass | pass | — |
| `presence_flags` | correct | pass | pass | pass | — |
| `m01_pop_keeps_count` | mutant | fail | pass | fail | `trace` cycle 4; `p_pop_full_count` |
| `m02_pushpop_full_push_wins` | mutant | fail | pass | fail | `trace` cycle 6; `p_pushpop_full_count` |
| `m03_pushpop_half_wrong_head` | mutant | fail | pass | fail | `trace` cycle 13; `p_pushpop_half_head` |
| `s01_ghost_law` | seeded | pass | fail | pass | L002 |
| `s02_untraceable` | seeded | pass | fail | pass | L003 |
| `s03_stale_hash` | seeded | pass | fail | pass | L014 |

`trace` and `formal` each reject all three mutants, from the same submitted file and
against independent claims — a 16-cycle simulation and a 12-step proof. Neither
subsumes the other in general, but on these three they agree, so neither is the sole
catcher; `lint` is the only gate that reads the metadata and it catches its three
alone. No gate rejects a correct implementation.

The first run of `presence_flags` failed `p_count_within_depth` and `p_full_iff_depth`,
and it was the RTL that was wrong: the occupancy was the two flags concatenated, so
full read as 3 rather than 2. The pack caught a real defect in an implementation
written to be correct, which is the reason the corrected design is an entry rather
than a quiet fix.

## What this does not cover

- **Trace is bounded by the plan.** Sixteen cycles, one sequence. A mutant that only
  diverges outside it would survive `trace`; the plan's full-queue case exists because
  that is exactly what happened to `m02` on the shorter plan.
- **Deep proofs.** `props_locked.sby` is BMC at depth 12. A correct implementation is
  accepted only to that depth; the mutants fail inside it.
- **A scored submission.** The submission here is a reference the corpus author wrote
  to exercise the pipeline. It is not a study-run artifact, and the gates being
  calibrated on it says nothing about a model's submission.
- **The seeded entries' behavioural pass.** The three seeded defects are law-metadata
  defects; neither `trace` nor `formal` reads the files they break. Their passing is
  expected, and a corpus cannot use it as evidence that the behavioural gates are weak.
