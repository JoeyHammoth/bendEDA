# toy_counter_laws corpus — `trace`, `formal` and `lint` over one submission (LA4)

The other two corpora name one gate each, so `per gate:` could only ever print one
line. This one names three, over the base submission
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
| `mutant/m03_truncates_increment` | **FAIL** | `a_eight_from_zero` and the sum property fire; `inc[1:0]` lost the value |
| `seeded/s03_wraps_at_16` | **FAIL** | `a_never_above_ceiling`: no saturation |
| `seeded/s04_drops_inc_msb` | **FAIL** | `a_eight_from_zero` at step 2, `props.sv:79` |
| `seeded/s05_resets_to_one` | **PASS** | no property mentions reset, so nothing forbids it |

The entries not listed (`correct/retiered`, `mutant/m02_priority_dropped`,
`seeded/s01_law_survives`) replace no RTL file, so the base's PASS applies to the
design they submit.

Two verdicts are the reason the corpus names more than one behavioural gate:

- **`s04` is formal-only.** Every value in `plan.json` is 4 or less, so keeping
  `inc[2:0]` changes nothing the simulator sees; the SVA pack asks for `inc == 8` and
  rejects the design. `trace` cannot see it, and that is not a defect in `trace`.
- **`s05` is trace-only.** Reset loads 1 instead of 0. The model has no reset state,
  so there is no law to translate and the pack says nothing about reset; every
  transition property still holds from an arbitrary state, so `formal` accepts it.
  `trace` rejects it at the first cycle, and the same defect is the mutant
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

## What this corpus does not do

- **It was not calibrated by `bendeda gate calibrate` in this revision.** The Docker
  engine on the authoring host would not start, so no GS/GSp and no `per gate:`
  contribution table is claimed here. The formal verdicts above are the verdicts of
  the job the gate runs; `bendeda gate run formal` adds the pinned container and the
  `PASS` marker read, which is what the gate's unit tests pin. The `trace` verdicts for
  the nine earlier entries are the ones recorded in the previous revision of this file,
  whose base RTL, model and plan are unchanged; `s04` and `s05` differ from the base
  only in `reset`/`inc`, and the `trace` argument for each is stated above.
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
