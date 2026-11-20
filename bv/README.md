# BendBV — the bit-vector library the models stand on

Bend has three numeric types and no arbitrary-width bit-vectors, so every model
that needs modular arithmetic needs a small library first. This directory will
hold `bv.bend` plus its proofs.

**Status: not written yet.** It is Phase 0.4 and is tracked as an issue; the plan
below is the specification it must satisfy.

## Representation (decided in Appendix K, G-01)

`BV(w)` is a `U32` with an explicit `mask(w)` applied on every operation:

```text
mask(w, x)        = x & ((1 << w) - 1)          # w <= 32
bv_add(w, a, b)   = mask(w, a + b)              # wraps as hardware does
bv_sub(w, a, b)   = mask(w, a - b)
```

Why `U32` and not `Nat`: the released guide states that `Nat` literals above
`256n` are `U32.to_nat` underneath and cap at `4294967295n`, and that `U32` is the
only released type carrying `and or xor not shl shr`. An earlier draft of the
design document assumed a `Nat` encoding below `2^w`; that assumption was wrong
and was corrected rather than quietly worked around.

## What must be proved

| Lemma | Statement |
|---|---|
| closure | `bv_add(w, a, b) < 2^w` for `a, b < 2^w` |
| commutativity | `bv_add(w, a, b) == bv_add(w, b, a)` |
| associativity | `bv_add(w, bv_add(w, a, b), c) == bv_add(w, a, bv_add(w, b, c))` |
| identity | `bv_add(w, a, 0) == a` |
| wrap | `bv_add(w, 2^w - 1, 1) == 0` |
| mask idempotence | `mask(w, mask(w, x)) == mask(w, x)` |

Plus FSM helpers: `step`, `run(init, inputs)`, `trace_equal`.

## Constraints

- Every definition must terminate under Bend's structural-recursion rule; no
  `@unsafe`.
- No escape hatches: a proof using one is invalid, not merely weak (Appendix H.8).
- Reduced widths for L2 exhaustive runs are declared per task, smallest values that
  still exhibit wrap-around.
- The library is visible to the implementation agent on purpose: a law that needs
  a lemma the agent cannot see is a design error, not a difficulty setting.
