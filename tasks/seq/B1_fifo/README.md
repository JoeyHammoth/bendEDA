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
python -m unittest tests.test_b1_fifo -v                  # 9 tests
```

`tests/test_b1_fifo.py` is what keeps the composition honest: it also composes
`negative/fifo_n01_strict_below_depth.bend` and requires a refusal with both
values.

## Gates

| Gate | Result | Evidence |
|---|---|---|
| **LA1** typing and proof | **pass** | 19/19 laws closed; `ALL PROOFS CHECK` on the composed book |
| **LA2** witnesses | **pass (model level)** | the 3 witnesses are closed laws: reaches full, reaches empty, reaches half |
| **LA3** model sensitivity | **not measured** | `law mutate` finds no site this catalogue can mutate (exit 3), because the model contains no arithmetic operator to swap |
| **LA4** design discrimination | skip | no seeded-bug corpus and no RTL |
| **LA5** implementation neutrality | skip | no three implementations |
| **LA6** coverage and parity | skip | C2 is provisional; parity would be confounded |
| **LA7** translation fidelity | skip | no SVA toolchain, so no TF traces |
| **LA8** provability cap | **pass** | longest reference proof is 8 lines; no law needs induction |
| **LA9** independence | skip | one session wrote every artifact |

Law coverage is 11 of 12 requirements, with R12 (pointer wrap-around) declared
conformance-only. `law lint` reports zero findings over all fifteen rules, with
one note: L006 was not evaluated because LA3 produced no mutation report.

## Why the model is a transition table

The occupancy is an ADT (`Empty`/`Half`/`Full`), not a `Nat`, and the laws are
stated per occupancy rather than quantified over it. That is what makes every
proof close by evaluation: a symbolic `Nat` comparison does not reduce without an
induction over `Nat.is_le`, and a law whose proof is harder than the property is
a liability under LA8. The cost is stated in the law file and in the research
note: the transition table is covered row by row, so a depth-parameterised model
and a quantified `count <= D` induction remain open work.

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
- **Mutation pressure (LA3).** The catalogue swaps arithmetic operators and bumps
  literals on arithmetic lines. A constructor table has neither, so the gate
  reports "nothing measured" rather than a kill rate. Mutating branches and
  constructor choices is the tool gap this package exposed.
- **Locking.** `locked/LOCKED.json` stays empty: locking needs LA1-LA9 and a
  Conductor, and neither is available.
