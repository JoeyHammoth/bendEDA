# B1_fifo — draft task package

The first complete task package: a synchronous FIFO with `W = 32`, reduced depth
`D = 2`. Status is **draft**, not `locked`. Nothing here is scored, and a run
against this package would be a rehearsal, not a result.

## Layout

| File | Role | State |
|---|---|---|
| `spec.md` | natural-language requirement, R1-R12 | complete |
| `model.bend` | reference model: `count`, `is_full`, `is_empty`, `dout`, `step`, `reset` | complete |
| `LAWS.bend` | 19 laws: 3 safety, 13 functional/refinement, 3 witnesses | complete, lint-clean |
| `PROOF_ref.bend` | reference proofs, one per law | complete, `ALL PROOFS CHECK` |
| `laws.manifest.yaml` | ids, classes, priorities, requirements, witnesses, translations | complete |
| `abs.yaml` | RTL-to-model abstraction map, assumptions, reduced parameters | complete |
| `props_locked.sv` | SVA translation of the laws, plus covers for the witnesses | complete, Yosys-elaborated, BMC pass |
| `props_locked.sby` | SymbiYosys job over that pack on the reference FIFO | complete, BMC depth 12 with z3, PASS |
| `props_c2.sv` | control pack written from the spec alone | provisional, see below |
| `provenance.yaml` | authoring chain | draft, single session |
| `variants.yaml` | seeded-variant declaration | declared, generator not implemented |
| `ambiguities.yaml` | four resolved ambiguities, with the rule applied | complete |
| `negative/` | one plausible but false law | refused, as intended |

## How to check it

The package is three files composed, because the harness gives the agent the
laws and hides the reference proofs, and `bend` at this pin cannot import the
model by path:

```bash
export BENDEDA_BUN=bun
export BENDEDA_BEND_CLI=.bend-cache/bend-2.0.40/bend2/main.ts
cat tasks/seq/B1_fifo/model.bend tasks/seq/B1_fifo/LAWS.bend \
    tasks/seq/B1_fifo/PROOF_ref.bend > /tmp/b1.bend
bun .bend-cache/bend-2.0.40/bend2/main.ts /tmp/b1.bend   # ALL PROOFS CHECK
python -m bendeda law lint tasks/seq/B1_fifo              # 0 findings
python -m unittest tests.test_b1_fifo -v                  # 10 tests

# LA3 needs the proofs, and `law mutate` takes one law file:
cat tasks/seq/B1_fifo/LAWS.bend tasks/seq/B1_fifo/PROOF_ref.bend > /tmp/laws.bend
python -m bendeda law mutate tasks/seq/B1_fifo/model.bend --laws /tmp/laws.bend --local \
    --out .bend-cache/b1/mutation.json
python -m bendeda law lint tasks/seq/B1_fifo --mutation .bend-cache/b1/mutation.json
```

`tests/test_b1_fifo.py` is what keeps the composition honest: it also composes
`negative/fifo_n01_strict_below_depth.bend` and requires a refusal with both
values.

## Gates

| Gate | Result | Evidence |
|---|---|---|
| **LA1** typing and proof | **pass** | 22/22 laws closed; `ALL PROOFS CHECK` on the composed book |
| **LA2** witnesses | **pass (model level)** | the 3 witnesses are closed laws: reaches full, reaches empty, reaches half |
| **LA3** model sensitivity | **pass** | 51 mutants, 51 killed, kill rate 1.00 against a 0.9 bar; the ten survivors of the previous run are killed by three post-state laws (below) |
| **LA4** design discrimination | **pass (corpus)** | `experiments/corpus/b1_fifo_rtl`: GS 1.000 (mutant 3/3, seeded 3/3), GSp 1.000 (3/3 correct) |
| **LA5** implementation neutrality | partial | three structurally different FIFOs are accepted by the same `lint` and `formal`, but one session wrote all three |
| **LA6** coverage and parity | skip | C2 is provisional; parity would be confounded |
| **LA7** translation fidelity | skip | the pack elaborates and its BMC passes, but no TF traces are computed |
| **LA8** provability cap | **pass** | longest reference proof is 8 lines; no law needs induction |
| **LA9** independence | skip | one session wrote every artifact |

Law coverage is every requirement except R12 (pointer wrap-around), which is
declared conformance-only. R13 was added to the specification because the idle
behaviour was stated without an id, and `fifo_f14` is its law. `law lint` reports
zero findings over all fifteen rules, with and without the full mutation report.

### LA3, measured

```console
$ cat LAWS.bend PROOF_ref.bend > /tmp/laws.bend
$ python -m bendeda law mutate model.bend --laws /tmp/laws.bend --local \
      --max-mutants 60 --out .bend-cache/b1/mutation_full.json
law mutate: 51 mutant(s), 51 killed by at least one law, kill rate 1.00
$ echo $?
0
```

51 is every site the catalogue reaches on this model (14 branch swaps, 34
constructor choices, 3 bare `Nat` literals), and the run costs ~50 minutes locally
because each mutant is 22 checker invocations. The bar is 0.9 and the gate passes —
but only after the laws changed, which is the interesting part.

The same catalogue killed 41 of 51 against the first law set. The ten survivors
were all constructor choices in `step`'s transition table, and none of them was an
equivalent mutant: at line 107, `Idle` on a full FIFO returned `Empty{}`; at line
85, `PushPop` on an empty FIFO stopped returning `Half{}`. Running the mutated model
against all 19 laws directly printed `ALL PROOFS CHECK` — the scorer was right and
the laws were the weak part.

The gap was one gap, not ten: the laws constrained the data (`head`, and `count` as
a *state* predicate) and never the occupancy a cycle produces. Three laws close it,
and each is killed by the mutants it was written for:

| Law | Requirement | Kills |
|---|---|---|
| `fifo_f14_idle_preserves_count` | R13 (added: idle leaves occupancy alone) | lines 87, 97, 107 — `Idle` on empty, half and full |
| `fifo_f15_pushpop_empty_count` | R11 | line 85 — `PushPop` on empty |
| `fifo_f16_pushpop_full_count` | R10 | line 105 — `PushPop` on full |

R13 had to be added to the specification as well: behaviour item 5 ("with neither
push nor pop, the state does not change") was stated without a requirement id, and
citing R9 for a law about occupancy would have been false.

**Correction (2026-11-24):** the first report said
`fifo_s01_count_within_depth` was *type-enforced*. That was wrong. `count` returns
`Nat`, nothing stopped it returning `3n`, and the catalogue simply never bumped a
bare `Nat` literal, which is what a `match` arm's whole body is here. With that
class added, `m006 literal 2n -> 3n` kills `fifo_s01` at the law layer
(`- expected : False{}`), and the law stays in the package. The earlier 0.875 came
from a narrower catalogue, and 0.804 was that wider catalogue measured against the
old laws. The 1.00 above is the same catalogue against 22 laws.

## Why the model is a transition table

The occupancy is an ADT (`Empty`/`Half`/`Full`), not a `Nat`, and the laws are
stated per occupancy rather than quantified over it. That is what makes every
proof close by evaluation: a symbolic `Nat` comparison does not reduce without an
induction over `Nat.is_le`, and a law whose proof is harder than the property is
a liability under LA8. The cost is stated in the law file and in the research
note: the transition table is covered row by row, so a depth-parameterised model
and a quantified `count <= D` induction remain open work.

## The parametric model, and why it is still open

Replacing `Level` with a `Nat` occupancy, at D = 2, makes the bound law *false*
over the type, because `MkFifo{a, b, n}` admits `n = 5`:

```console
$ bun main.ts .bend-cache/scratch/fifo_nat_probe.bend
SOME PROOFS FAIL
- expected : Cmp.is_le(Nat.cmp(count(s), 2n))
- observed : True{}
```

Recursing on the occupancy, as cookbook S3 does, produces a hypothesis about the
wrong bound, because the structural descent lowers the argument while the law's
literal stays at 2: the goal becomes `le(p, 2n)` from a hypothesis `le(p, 1n)`. A
parametric model therefore needs the bound in the type (a length-indexed vector, or
a proof field) or a reachable-state invariant plus `le`-monotonicity lemmas. That is
research work, and it is why the reduced ADT remains the only shape whose laws
close by evaluation here.

## What is not done, and why

- **Reference proofs by an independent RPA run.** The `PROOF_ref.bend` here was
  written in the same session as the laws. It is a correct reference proof, and
  it is not an independent one.
- **C2 authored from the spec alone by a different run.** `props_c2.sv` names no
  model symbol, but the same session wrote it after the laws, so LC(C2) versus
  LC(C3) parity is confounded and must not be reported.
- **The oracle pack and the seeded-bug corpus.** No OAA artifact exists, so
  LA4/LA5 cannot run and `variants.yaml` declares its generator rather than
  implementing it.
- **SVA coverage.** `props_locked.sv` is now written in the subset the pinned Yosys
  parses, elaborates, and its BMC job passes on a reference FIFO; `props_c2.sv` is
  still unelaborated. Elaboration is not LA7: no TF traces are computed, so translation
  fidelity remains unmeasured, and the `.sby` job is run against a scratch reference,
  not against a scored submission.
- **An independent LA3 result.** The gate passes at 1.00 on this catalogue, but the
  laws and their proofs came from one session, so the number says the law set
  constrains the model — not that a second author would have written these laws.
- **Locking.** `locked/LOCKED.json` stays empty: locking needs LA1-LA9 and a
  Conductor, and neither is available.
