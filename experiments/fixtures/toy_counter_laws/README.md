# toy_counter_laws — RTL, an SVA pack and a law package in one submission

`experiments/fixtures/toy_counter` proves the vector path: a Bend model, RTL and a
port manifest, judged by `trace`. `tasks/seq/B1_fifo` carries a law package but no
RTL, so `lint` has a corpus and `trace` has a different one. This fixture is the
smallest submission that has both, and with `counter.sby` it is also the only
submission in the repository that has all three: a model/RTL pair for `trace`, an
SVA pack for `formal`, and a law package for `lint`. One corpus can therefore
judge three gates on the same entries.

| File | Role |
|---|---|
| `spec.md` | requirement list R1-R4 |
| `model.bend` | the reference model: `step(count, inc) = min(count + inc, 15)` |
| `dut.sv` | the RTL, copied from `experiments/fixtures/toy_counter` |
| `dut.json` | the port manifest the generated testbench reads |
| `plan.json` | the stimulus plan |
| `props.sv` | SVA translations of the five transferable laws, plus R2 at an increment the plan never applies |
| `counter.sby` | the SymbiYosys job that checks `props.sv` against the DUT |
| `LAWS.bend` | 5 laws and 3 witnesses |
| `PROOF_ref.bend` | one same-name proof per law |
| `laws.manifest.yaml` | ids, classes, priorities, requirements, witnesses, translations, hashes |
| `provenance.yaml` | authoring chain |

It is a fixture, not a study task: nothing here is scored, there are four
requirements, and the laws are closed over literals because a law quantified over a
symbolic `U32` needs an induction over `U32.is_gt` that the checker does not close
for free (the trade-off `spec.md` records).

## How to check it

```console
$ python -m bendeda law lint experiments/fixtures/toy_counter_laws
experiments/fixtures/toy_counter_laws: 8 law(s), 0 finding(s)
  note: L006 not evaluated: no mutation report was supplied ...
law lint: 1 package(s), 8 law(s), 0 finding(s)

$ cat model.bend LAWS.bend PROOF_ref.bend > /tmp/sat.bend
$ bun .bend-cache/bend-2.0.40/bend2/main.ts /tmp/sat.bend
ALL PROOFS CHECK

$ python -m bendeda gate run trace --artifacts experiments/fixtures/toy_counter_laws
gate trace: pass

$ (cd experiments/fixtures/toy_counter_laws && sby -f -d /tmp/sat_out counter.sby)
...
SBY ... engine_0: ##   0:00:00  Status: passed
SBY ... engine_0: Status returned by engine: pass
SBY ... summary: engine_0 (smtbmc z3) returned pass
SBY ... DONE (PASS, rc=0)
```

The last command is the job `bendeda gate run formal` executes inside the pinned
image; the gate requires that image, because it runs `sby` there and reads the `PASS`
marker. In this revision it was run with the WebAssembly build of the same SymbiYosys
(`yowasp-sby`, solver z3) because the authoring host's Docker engine was unavailable;
the job file, the pack and the verdict marker are unchanged.

`lint` says L006 was not evaluated, and that is the honest report: this fixture's
own package does not ship a mutation report, so no rule checked whether its laws
constrain the model. The report exists — it is the catalogue below — and the corpus
entry `experiments/corpus/toy_counter_laws/seeded/s01_law_survives` carries it,
because on this package L006 fires.

The manifest names the assertion for each transferable law (`translation.sva`), and
`props.sv` is where those assertions live. The three witness laws are `L-WIT` and are
not translated: a witness is a reachability claim, not a property to prove on the RTL.

## The full mutation catalogue

The model has four definitions, so the catalogue has four sites and this is the
whole of it, not a sample:

```console
$ cat LAWS.bend PROOF_ref.bend > /tmp/sat_laws.bend
$ python -m bendeda law mutate model.bend --laws /tmp/sat_laws.bend --local \
      --max-mutants 48 --out .bend-cache/sat/full.json
law mutate: 4 mutant(s), 3 killed by at least one law, kill rate 0.75, 1 law(s) survived every mutant
```

| Mutant | Edit | Line | Laws that falsify it |
|---|---|---|---|
| `m001` | `literal 15 -> 16` on `limb`'s result | 16 | none |
| `m002` | `swap arms True{} / False{}` in `pick` | 20 | 7 of 8 (all but `counter_f02_exact_fit_reaches_ceiling`) |
| `m003` | `literal 15 -> 16` in `pick`'s `True` arm | 21 | `counter_s01_never_above_ceiling`, `counter_s02_ceiling_holds_under_max_increment` |
| `m004` | `literal 15 -> 16` in `step`'s `U32.is_gt` bound | 26 | `counter_s01_never_above_ceiling` |

Seven of the eight laws are falsified by at least one of these four edits.

Two results deserve to be stated rather than averaged:

- **`m001` is an equivalent mutant for this law set.** It edits `limb`, which no law
  calls — the definition exists so the vector driver can check that `Nat` and `U32`
  cross the JS boundary. Its survival is not evidence about the laws, and the 0.75
  kill rate understates them because of it.
- **`counter_f02_exact_fit_reaches_ceiling` survives all four, and that is a real
  finding.** `step(14, 1) == 15` holds with a threshold of 16, with `pick`'s arms
  swapped, and with `pick`'s `True` arm mutated, because every one of those still
  returns 15 on this input. The law is true and does not constrain the model — which
  is exactly the condition L006 reports.

The run exits 1 and the report's `ok` is false, but neither is a claim that a law is
false. Both come from the pre-registered bar of 20 mutants and a 0.9 kill rate; a
four-definition model cannot reach 20 sites. The bar is meaningful for a study task
(`tasks/seq/B1_fifo` has 51 sites); for this fixture the useful statement is the
per-law one above.
