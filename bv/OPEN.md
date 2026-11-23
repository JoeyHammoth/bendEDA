# BendBV — claims that are not proved yet

Phase 0 exit criterion 3 wants every BendBV lemma to check with no escape hatch.
Everything in `bv.bend` checks. This file lists the claims the library still does
**not** make, so a model cannot rely on one by accident.

None of these are laws in `bv.bend` on purpose: an open law prints the same
`SOME PROOFS FAIL` as a deleted mask, which would blur the difference between
proved and hoped.

## Proved since the first version (2026-11-24)

| Lemma | Statement |
|---|---|
| `mask.w0` | `mask(0n, x) == 0` |
| `mask.w32` | `mask(32n, x) == x` — a shift by 32 gives 0, so `1 - 0` wraps to all ones |
| `Word.and_zero`, `Word.and_one` | `Word.and` with the zero word clears, with the all-ones word preserves |
| `Word.adc_zero`, `Word.add_zero`, `U32.add_zero` | the additive identity, through the carry chain |
| `bv_add.id_zero` | `bv_add(w, mask(w, a), 0) == mask(w, a)` |
| `bv_add.in_range`, `bv_sub.in_range` | the result is already in the masked subalgebra |
| `bv_add.assoc8_instance` | one concrete 8-bit association, decided by evaluation |

## Still open

| Claim | Status | What it is missing |
|---|---|---|
| closure as a numeric bound: `Word.to_nat(32n, bv_add(...)) < 2^w` | open | `Word.to_nat` ships with no laws, and nothing at the pin connects `Word.and` against the mask to a `Nat` bound. The library states the form it can prove — mask idempotence on the result — and does not state the form it cannot. |
| associativity of `Word.add` | open | carry propagation through `Word.adc`; Base proves commutativity only, and `Bool.full_add` has no laws. `bv_add.assoc8_instance` is a check that one evaluation agrees, not the universal law. |
| symbolic wrap: `bv_add(w, 2^w - 1, 1) == 0` | open | the same `Word.adc` carry theory, plus a term for `2^w` (see closure). The 8-bit form is decided by evaluation and is in the library as `bv_add.wrap8`. |
| FSM helpers `step`, `run`, `trace_equal` | deferred to Phase 1 | Bend has no polymorphic fold over `List` usable across state types, so a `run` for `U32` state cannot be shared with one for a record. The first task package fixes the state type. |

The width contract is therefore carried in two pieces: `bv_add.in_range` and
`bv_sub.in_range` say the operation returns a masked value, and `bv_add.id_zero`
says the masked values form a monoid with zero. A numeric bound would be a
stronger statement, and it is not proved.
