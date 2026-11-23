# BendBV — the bit-vector library the models stand on

Bend has three numeric types and no arbitrary-width bit-vectors, so every model
that needs modular arithmetic needs a small library first. `bv.bend` is that
library, with its claims and proofs in one file.

**Status: every lemma in the file checks.** `bend bv/bv.bend` prints
`ALL PROOFS CHECK` on the pinned Bend 2.0.40, and
`bend bv/negative/unmasked_add.bend` prints `SOME PROOFS FAIL` — the control
deletes `mask(w)` and must not pass. What is still unproved is in `OPEN.md`,
each claim beside the base lemma it is missing. The library states the width
contract in the form the pin can support (the mask leaves its own results
alone), not as a numeric bound it cannot prove.

## Representation (decided in Appendix K, G-01)

`BV(w)` is a `U32` with an explicit `mask(w)` applied on every operation:

```text
mask(w, x)        = x & (2^w - 1)               # w <= 32
bv_add(w, a, b)   = mask(w, a + b)              # wraps as hardware does
bv_sub(w, a, b)   = mask(w, a - b)
```

`mask` is computed in `U32`, so `w = 0` gives `0` and `w = 32` wraps the shift to
`0`, making the mask `0xFFFFFFFF` — the identity. Widths above 32 are out of
scope for v1.

Why `U32` and not `Nat`: the released guide states that `Nat` literals above
`256n` are `U32.to_nat` underneath and cap at `4294967295n`, and that `U32` is the
only released type carrying `and or xor not shl shr`. An earlier draft of the
design document assumed a `Nat` encoding below `2^w`; that assumption was wrong
and was corrected rather than quietly worked around.

## What checks

| Lemma | Statement |
|---|---|
| `Bool.and_idem`, `Bool.and_comm`, `Bool.and_assoc` | the bitwise laws Base does not ship |
| `Bool.and_false`, `Bool.and_true` | `Word.and`'s absorbing and identity bit |
| `Word.and_idem` | `Word.and(n, a, a) == a`, by structural induction on the word |
| `Word.and_assoc` | `Word.and(n, Word.and(n, a, b), c) == Word.and(n, a, Word.and(n, b, c))` |
| `Word.and_zero`, `Word.and_one` | `Word.and` with zero clears; with all ones preserves |
| `mask.idem` | `mask(w, mask(w, x)) == mask(w, x)` |
| `mask.w0`, `mask.w32` | `mask(0n, x) == 0` and `mask(32n, x) == x` |
| `Word.adc_zero`, `Word.add_zero`, `U32.add_zero` | the additive identity through the carry chain |
| `bv_add.comm` | `bv_add(w, a, b) == bv_add(w, b, a)` |
| `bv_add.id_zero` | `bv_add(w, mask(w, a), 0) == mask(w, a)` |
| `bv_add.in_range`, `bv_sub.in_range` | the result is already a masked value |
| `bv_add.wrap8` | `bv_add(8n, 200, 100) == 44` — the concrete 8-bit wrap |
| `bv_add.assoc8_instance` | one concrete 8-bit association, by evaluation |

## The negative control

`negative/unmasked_add.bend` is the library with `mask(w)` deleted and the same
8-bit wrap claim. It prints `SOME PROOFS FAIL` with `expected 300, observed 44`.
A numeric closure bound, symbolic wrap and associativity are not proved yet (see
`OPEN.md`), so the concrete claims are what would catch a missing mask in the
arithmetic itself; the gate refuses the control in `tests/test_bv.py` and in CI.

## Why one file, not `LAWS.bend` plus `PROOF.bend`

The guide's two-file convention assumes `PROOF.bend` can import `LAWS.bend`. On
2.0.40 that import resolves against the working directory rather than the
importing file, and a path containing `.bend` is rejected outright —

```text
expected : an import path of plain names (each starts with a letter or _, then letters, digits, _ and -)
observed : 'LAWS.bend'
```

— so a split would check only when the gate happened to run in a particular
directory, and a CI job that got it wrong would report a pass it had not earned.
One file checks identically from anywhere.

## Constraints

- Every definition terminates under Bend's structural-recursion rule; no
  `@unsafe`.
- No escape hatches: a proof using one is invalid, not merely weak (Appendix H.8).
- Law-filling defs are untyped, and a parameter reused more than once needs a `+`
  binding (`case U32{+xw}`, `+ww = w`) because Bend bindings are affine. This is
  the idiom Base uses in `U32.popcount`, and it is not stated in the guide.
- Reduced widths for L2 exhaustive runs are declared per task, smallest values
  that still exhibit wrap-around.
- The library is visible to the implementation agent on purpose: a law that needs
  a lemma the agent cannot see is a design error, not a difficulty setting.
