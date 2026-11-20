# BendBV — claims that are not proved yet

Phase 0 exit criterion 3 wants every BendBV lemma to check with no escape hatch.
These are the claims still outstanding and the base lemma each one is missing.
They are deliberately **not** in `bv.bend`: an open law makes the gate print
`SOME PROOFS FAIL`, which would blur the difference between proved and hoped.

| Claim | What it is missing |
|---|---|
| closure: `bv_add(w, a, b) < 2^w` | `Word.and` with a mask clears every bit at or above `w`; and the library has no term for `2^w` (Bend's `U32.pow` takes a `U32` base, not a `Nat` exponent) |
| identity: `bv_add(w, a, 0) == a` for `a < 2^w` | absorption, `Word.and(n, a, maskbits) == a` when `a` fits, which needs closure first |
| wrap: `bv_add(w, 2^w - 1, 1) == 0` | `Word.add` of all-ones and one; Base proves commutativity only, and `Bool.full_add` has no laws |
| associativity | `Word.add` associativity, which needs `Bool.full_add` laws that do not exist |
| `mask(0, x) == 0` and `mask(32, x) == x` | `Word.and` with the zero word and with the all-ones word |
| FSM helpers `step`, `run`, `trace_equal` | Bend has no polymorphic fold over `List` usable across state types, so a `run` for `U32` state cannot be shared with one for a record. Deferred to Phase 1 with the first task package, which fixes the state type |

The laws that are proved are the ones the mask layer needs in order to say
anything at all: masking twice changes nothing, and a masked add commutes.
Neither is a substitute for closure, which is the lemma that actually states the
width contract.
