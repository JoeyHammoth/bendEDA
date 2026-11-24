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
| `props_locked.sv` | SVA translation of the laws, plus covers for the witnesses | written, **not elaborated** |
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
| **LA1** typing and proof | **pass** | 19/19 laws closed; `ALL PROOFS CHECK` on the composed book |
| **LA2** witnesses | **pass (model level)** | the 3 witnesses are closed laws: reaches full, reaches empty, reaches half |
| **LA3** model sensitivity | **fail** | 51 mutants, 41 killed, kill rate 0.804 against a 0.9 bar; no law survived every mutant, and 10 constructor-choice mutants survived every law (below) |
| **LA4** design discrimination | skip | no seeded-bug corpus and no RTL |
| **LA5** implementation neutrality | skip | no three implementations |
| **LA6** coverage and parity | skip | C2 is provisional; parity would be confounded |
| **LA7** translation fidelity | skip | no SVA toolchain, so no TF traces |
| **LA8** provability cap | **pass** | longest reference proof is 8 lines; no law needs induction |
| **LA9** independence | skip | one session wrote every artifact |

Law coverage is 11 of 12 requirements, with R12 (pointer wrap-around) declared
conformance-only. `law lint` reports zero findings over all fifteen rules, and it
still reports zero with the full mutation report: every law is killed by at least
one mutant. The LA3 failure is the other direction — mutants no law kills.

### LA3, measured

```console
$ cat LAWS.bend PROOF_ref.bend > /tmp/laws.bend
$ python -m bendeda law mutate model.bend --laws /tmp/laws.bend --local \
      --max-mutants 60 --out .bend-cache/b1/mutation_full.json
law mutate: 51 mutant(s), 41 killed by at least one law, kill rate 0.80
$ echo $?
1
```

51 is every site the catalogue reaches on this model (14 branch swaps, 34
constructor choices, 3 bare `Nat` literals), and the run costs ~40 minutes locally
because each mutant is 19 checker invocations. The bar is 0.9, so the gate fails.
That is the measured result, not a threshold to argue with.

The ten survivors are all constructor choices in `step`'s transition table, and
they are not equivalent mutants — each changes behaviour the specification pins:

| Line | Mutation | What the model then does | Why no law notices |
|---|---|---|---|
| 85, 87 | `Half{}` -> `Empty{}` / `Full{}` | `PushPop` on empty no longer leaves `Half` | `f13` states the head, not the occupancy |
| 97 | `Half{}` -> `Empty{}` / `Full{}` | `Idle` on half no longer leaves `Half` | `f12` states the head is preserved |
| 105 | `Half{}` -> `Empty{}` / `Full{}` | `PushPop` on full no longer leaves `Half` | no law states the post-state occupancy |
| 107 | `Full{}` -> `Empty{}` / `Half{}` | `Idle` on full empties the FIFO | `f12` keeps `a` and `b`, which this mutant keeps too |

The gap is one gap, not ten: the laws constrain the data (`head`, and `count` as a
*state* predicate) but never say what occupancy a cycle produces. `Idle` and a
`Push` on full must leave the level alone, and no law says so. Killing these needs
laws of the form `count(step(s, Idle{})) == count(s)` — or the level itself as a
value — which is new law authoring, not a catalogue change.

**Correction (2026-11-24):** the first report said
`fifo_s01_count_within_depth` was *type-enforced*. That was wrong. `count` returns
`Nat`, nothing stopped it returning `3n`, and the catalogue simply never bumped a
bare `Nat` literal, which is what a `match` arm's whole body is here. With that
class added, `m006 literal 2n -> 3n` kills `fifo_s01` at the law layer
(`- expected : False{}`), and the law stays in the package. The earlier 0.875 came
from a narrower catalogue; this 0.804 is the wider one, and it is worse.

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
- **SVA elaboration.** No SystemVerilog toolchain is installed locally; the OSS
  CAD image has not been asked to elaborate `props_locked.sv` or `props_c2.sv`.
- **A clean LA3 pass.** The gate fails at 0.804 over the full catalogue. The ten
  survivors are unkilled because no law constrains the occupancy a cycle produces;
  closing that needs post-state laws (and their proofs), then a re-run. The
  `s01` question is settled — the law is falsifiable and now killed — and the
  earlier "type-enforced" reading is superseded in the table above.
- **Locking.** `locked/LOCKED.json` stays empty: locking needs LA1-LA9 and a
  Conductor, and neither is available.
