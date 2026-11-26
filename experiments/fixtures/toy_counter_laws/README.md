# toy_counter_laws — RTL and a law package in one submission

`experiments/fixtures/toy_counter` proves the vector path: a Bend model, RTL and a
port manifest, judged by `trace`. `tasks/seq/B1_fifo` carries a law package but no
RTL, so `lint` has a corpus and `trace` has a different one. This fixture is the
smallest submission that has both, which is what lets one corpus judge two gates:
the same entry can fail `trace` on its RTL and `lint` on its law package.

| File | Role |
|---|---|
| `spec.md` | requirement list R1-R4 |
| `model.bend` | the reference model: `step(count, inc) = min(count + inc, 15)` |
| `dut.sv` | the RTL, copied from `experiments/fixtures/toy_counter` |
| `dut.json` | the port manifest the generated testbench reads |
| `plan.json` | the stimulus plan |
| `LAWS.bend` | 5 laws and 3 witnesses |
| `PROOF_ref.bend` | one same-name proof per law |
| `laws.manifest.yaml` | ids, classes, priorities, requirements, witnesses, hashes |
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
```

`lint` says L006 was not evaluated, and that is the honest report: the law package
does not ship a mutation report, so no rule checked whether its laws constrain the
model. `experiments/corpus/toy_counter_laws/seeded/s01_law_survives` is the entry
that supplies one, and L006 fires there.

The manifest declares `translation_reason` rather than a `translation` for each law:
this fixture ships no SVA pack, and naming a property that does not exist would be a
claim nobody can check. L011 accepts either; it does not accept silence.
