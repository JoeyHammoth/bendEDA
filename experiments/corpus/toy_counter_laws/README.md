# toy_counter_laws corpus — `trace`, `formal` and `lint` over one submission (LA4)

The other corpora name one gate or two, so this is the one where `per gate:` has
three gates to compare. This one names three, over the base submission
`experiments/fixtures/toy_counter_laws` — the counter's model and RTL, an SVA pack and
a law package over that same model — so a mutant can fail `trace`, a design that is
right inside the simulated window can fail `formal`, and a seeded defect can fail
`lint`, all on the same corpus.

| Kind | What it is | Count |
|---|---|---|
| `correct` | submissions the gates accept, structurally different from each other | 3 |
| `mutant` | one small edit to the reference RTL or to the law metadata | 3 |
| `seeded` | a plausible authoring defect: a wrapping counter, a ghost law, stale mutation evidence, an increment bit and a reset the properties do not state | 5 |

`corpus.json` names the base, the gate set (`["trace", "formal", "lint"]`) and the
entries.

## The formal gate, measured

The `.sby` job was run over the staged entries — the base files with the entry's
overrides copied on top — with SymbiYosys and z3:

```console
$ sby -f -d out counter.sby
...
SBY ... engine_0: ##   0:00:00  Status: passed
SBY ... engine_0: Status returned by engine: pass
SBY ... summary: engine_0 (smtbmc z3) returned pass
SBY ... DONE (PASS, rc=0)
```

| Entry | `sby` verdict | What decided it |
|---|---|---|
| `correct/as_shipped` | **PASS** | every translated law holds on the reference RTL |
| `correct/compare` | **PASS** | different RTL (a five-bit comparison), same properties |
| `mutant/m01_adds_one` | **FAIL** | `a_sum_when_it_fits`: `3 + 4` came out as 8 |
| `mutant/m03_truncates_increment` | **FAIL** | `a_eight_from_zero`: `inc[1:0]` lost the value |
| `seeded/s03_wraps_at_16` | **FAIL** | `a_ceiling_under_max_increment`: 15 + 15 wrapped to 14 |
| `seeded/s04_drops_inc_msb` | **FAIL** | `a_eight_from_zero` at step 2 |
| `seeded/s05_resets_to_one` | **PASS** | no property mentions reset, so nothing forbids it |

The entries not listed (`correct/retiered`, `mutant/m02_priority_dropped`,
`seeded/s01_law_survives`) replace no RTL file, so the base's PASS applies to the
design they submit.

`a_never_above_ceiling` is not what rejects the wrapping counter, and that is worth
saying: a 4-bit register cannot hold a value above 15, so the ceiling assertion is
true by construction and no 4-bit RTL can falsify it. It is a faithful translation of
R1 and it is vacuous on this implementation; the transition assertions are what make
the pack non-vacuous. The weak assertion is not removed, because removing it would
remove the law's only RTL claim; the corpus records which assertion does the work.

Two verdicts are the reason the corpus names more than one behavioural gate:

- **`s04` is formal-only.** Every value in `plan.json` is 4 or less, so keeping
  `inc[2:0]` changes nothing the simulator sees; the SVA pack asks for `inc == 8` and
  rejects the design. `trace` cannot see it, and that is not a defect in `trace`.
- **`s05` is trace-only.** Reset loads 1 instead of 0. The model has no reset state,
  so there is no law to translate and the pack says nothing about reset; every
  transition property still holds from an arbitrary state, so `formal` accepts it.
  `trace` rejects it at the first compared cycle, and the same defect is the mutant
  `corpus/toy_counter/mutant/m02_resets_to_one`, which that corpus's calibration
  rejects.

So neither of the two behavioural gates subsumes the other on this corpus: one is
stronger where the properties are, the other is stronger where the model has state the
properties do not name.

## `seeded/s01_law_survives` and L006

L006 — "a law survived every model mutant" — cannot run without a mutation report,
and this package ships none at the fixture root: the linter says so with a note rather
than passing silently. This entry supplies one, and it is the real output of the full
catalogue over `model.bend`, not a one-mutant sample:

```console
$ cat LAWS.bend PROOF_ref.bend > /tmp/sat_laws.bend
$ python -m bendeda law mutate model.bend --laws /tmp/sat_laws.bend --local \
      --max-mutants 48 --out mutation.json
law mutate: 4 mutant(s), 3 killed by at least one law, kill rate 0.75, 1 law(s) survived every mutant
```

The report has four mutants and one surviving law. Fed to the linter, the rule fires
once:

```console
$ python -m bendeda law lint <base + this entry> --mutation mutation.json
L006 [counter_f02_exact_fit_reaches_ceiling]: law survived all 4 model mutants, so it does not constrain the model
```

Seven of the eight laws are falsified by at least one mutant. The eighth,
`counter_f02_exact_fit_reaches_ceiling`, is true under every one of them —
`step(14, 1) == 15` still holds with a threshold of 16, with `pick`'s arms swapped, and
with `pick`'s `True` arm mutated. That is a law that does not constrain the model, which
is what L006 exists to report; it is not a claim that the law is false. The fixture's
README records the one mutant that no law could have killed (`limb` is not called by a
law) and why the 0.75 rate understates the set.

Only this entry carries a report. A report on a `correct` entry would be judged too,
and this catalogue fails L006, so a correct entry carrying it would be a false reject.

## Calibrated

`bendeda gate calibrate` ran on this corpus with Docker up, the OSS CAD image present,
and the pinned Bun and compiler exported:

```console
$ export BENDEDA_BUN=.bend-cache/bunenv/node_modules/.bin/bun
$ export BENDEDA_BEND_CLI=.bend-cache/bend-2.0.40/bend2/main.ts
$ python -m bendeda gate calibrate --corpus experiments/corpus/toy_counter_laws
...
  per gate:
    trace      caught 4 bug(s), 1 of them alone; rejected 0 correct implementation(s)
    formal     caught 4 bug(s), 1 of them alone; rejected 0 correct implementation(s)
    lint       caught 3 bug(s), 3 of them alone; rejected 0 correct implementation(s)
gate calibrate: GS 1.000 (mutant 1.000 3/3, seeded 1.000 5/5), GSp 1.000 (3/3 correct)
$ echo $?
0
```

Every bug is rejected by at least one gate and no correct implementation is rejected.
`trace` and `formal` each catch four of the eight, and each catches exactly one that
the other does not — `s05` for `trace`, `s04` for `formal` — which is the reason this
corpus names both. `lint` catches its three alone, because neither behavioural gate
reads the metadata it judges.

## What this corpus does not do

- **Calibration needs the pinned toolchain.** Without `BENDEDA_BUN` and
  `BENDEDA_BEND_CLI`, `trace` skips, the correct entries become undecidable, and the
  command exits 3 without a GSp; the first attempt on this host did exactly that and
  is not the run recorded above. The verdicts above are from one run, on one host.
- It is a fixture, not a study task: 4 requirements, 5 laws, and laws closed over
  literals because a symbolic `U32` needs an arithmetic induction the checker does not
  close for free. A study task's corpus adds the MCY mutant set for that task.
- The correctness of the law package is not measured here. `lint` judges structure
  and record integrity; whether a law is *true* is the proof ladder's job
  (`ALL PROOFS CHECK` on `model.bend + LAWS.bend + PROOF_ref.bend`).
- `trace` is bounded by `--sim-timeout` (default 900s). Each entry simulates in the
  pinned image, and one hung DUT becomes a rejected entry naming the limit rather
  than a calibration that never ends.
- The files that declare hashes must be byte-exact. Written with the platform's line
  ending, `LAWS.bend` hashes differently on Windows than on Linux and L014 fails on one
  host only.
