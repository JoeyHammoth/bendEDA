# toy_counter_laws corpus — `trace` and `lint` over one submission (LA4)

The other two corpora name one gate each, so `per gate:` could only ever print one
line. This one names two, over the base submission
`experiments/fixtures/toy_counter_laws` — the counter's model and RTL plus a law
package over that same model — so a mutant that fails `trace` and a seeded defect
that fails `lint` are judged on the same entries.

| Kind | What it is | Count |
|---|---|---|
| `correct` | submissions both gates accept, structurally different from each other | 3 |
| `mutant` | one small edit to the reference RTL or to the law metadata | 3 |
| `seeded` | a plausible authoring defect: a wrapping counter, a ghost law, stale mutation evidence | 3 |

`corpus.json` names the base, the gate set (`["trace", "lint"]`) and the entries.

```console
$ bendeda gate calibrate --corpus experiments/corpus/toy_counter_laws
gate calibrate: toy_counter_laws from experiments/corpus/toy_counter_laws, gates trace, lint
  correct/as_shipped                 accepted    trace: pass, lint: pass
  correct/compare                    accepted    trace: pass, lint: pass
  correct/retiered                   accepted    trace: pass, lint: pass
  mutant/m01_adds_one                rejected    trace: fail, lint: pass — model and DUT disagree at cycle 0
  mutant/m02_priority_dropped        rejected    trace: pass, lint: fail — L012 laws.manifest.yaml [counter_s02_ceiling_holds_under_max_increment]: priority is None; expected one of ['core', 'extended', 'important']
  mutant/m03_truncates_increment     rejected    trace: fail, lint: pass — model and DUT disagree at cycle 4
  seeded/s01_law_survives            rejected    trace: pass, lint: fail — L006 [counter_s01_never_above_ceiling]: law survived all 1 model mutants, so it does not constrain the model
  seeded/s02_ghost_law               rejected    trace: pass, lint: fail — L002 laws.manifest.yaml [counter_f04_ceiling_is_sticky]: manifest entry has no law in the file
  seeded/s03_wraps_at_16             rejected    trace: fail, lint: pass — model and DUT disagree at cycle 7
  per gate:
    trace      caught 3 bug(s), 3 of them alone; rejected 0 correct implementation(s)
    lint       caught 3 bug(s), 3 of them alone; rejected 0 correct implementation(s)
gate calibrate: GS 1.000 (mutant 1.000 3/3, seeded 1.000 3/3), GSp 1.000 (3/3 correct)
```

Each gate catches half the corpus and catches it alone, which is the property the
table exists to show: the union rejects every bug, and neither member is decoration.
A one-gate corpus cannot make that distinction, because `sole_catch` equals `catch`
by construction.

The three correct entries differ in what they change: `as_shipped` is the base
unmodified, `compare` saturates on a five-bit comparison instead of the overflow
bit, and `retiered` re-tiers one law `important` → `extended` with its claims
untouched. Both gates accept all three, so neither gate is fitted to one wording of
the design.

## `seeded/s01_law_survives` and L006

L006 — "a law survived every model mutant" — cannot run without a mutation report,
and the linter says so: the fixture's own package reports `L006 not evaluated`. This
entry supplies `mutation.json`, which the lint gate now hands to the linter.

The report is the real output of

```console
$ python -m bendeda law mutate experiments/fixtures/toy_counter_laws/model.bend \
    --laws <LAWS.bend + PROOF_ref.bend> --local --max-mutants 1 \
    --out mutation.json
```

so its `total` is 1 and its `killed_by` is 0 for every law: the one mutant it
contains (a bare literal swapped in `pick`) is not noticed by any law in the
package. That is a true statement about that report, and L006 fails the entry on it.
It is not a kill rate for the law set, and this README would be lying if it called
it one.

Only this entry carries a report. A report on a `correct` entry would be judged too,
and a one-mutant report is not evidence that the package is adequate.

## What this corpus does not do

- It is a fixture, not a study task: 3 requirements, 5 laws, and laws closed over
  literals because a symbolic `U32` needs an arithmetic induction the checker does
  not close for free. A study task's corpus adds the MCY mutant set for that task.
- It never names `formal`: the fixture has no `.sby` job. A corpus whose task has
  proofs adds that gate to `gates`.
- The correctness of the law package is not measured here. `lint` judges structure
  and record integrity; whether a law is *true* is the proof ladder's job
  (`ALL PROOFS CHECK` on `model.bend + LAWS.bend + PROOF_ref.bend`).
- `trace` is bounded by `--sim-timeout` (default 900s). Each entry here simulates in
  the pinned image, and one hung DUT becomes a rejected entry naming the limit rather
  than a calibration that never ends.
