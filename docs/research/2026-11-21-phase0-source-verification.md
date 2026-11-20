# Phase 0 source verification — Bend 2 facts that change the plan

**Checked:** 2026-11-21 · **Purpose:** close the ⚠ claims in the design document before any harness code is written.

The design document (v0.3) carried a number of claims marked ⚠ — recalled rather than verified. This note lists what the primary sources actually say, what that changes, and what remains unverifiable. The normative version of these findings is Appendix K of `bend2-agentic-eda-research-design.md`; this file is the working record with quotes and links.

## Sources

| Ref | Source | Why it counts as primary |
|---|---|---|
| S1 | [bendlang/bend `guide/GUIDE.md`](https://github.com/bendlang/bend/blob/main/guide/GUIDE.md) | The released language guide, in the project's own repository |
| S2 | [bend2.dev — What is Bend2?](https://bend2.dev/notes/what-is-bend2/) | Project notes site (updated 2026-11-09) |
| S3 | [bend2.dev — syntax primer](https://bend2.dev/notes/bend2-syntax-primer/) | Project notes site, checked against released source |
| S4 | [bend2.dev — Bend2 vs Lean](https://bend2.dev/notes/bend2-vs-lean/) | Project notes site |
| S5 | [bend2.dev — types as specifications](https://bend2.dev/learn/types-as-specifications) | Project learn page with a worked law/proof pair |
| S6 | [Built with Bend — Bend 2 Proofs](https://builtwithbend.com/blog/bend-2-proof-workflow), 2026-11-03, Bend 2.0.39 | One dated third-party reproduction with exact commands and failures |

S6 is a single reproduction on one platform. It is used to *raise a question*, never to settle one — which is exactly why Phase 0 re-measures `--verdict` instead of inheriting its conclusion.

## Corrections that change the design

### 1. `Nat` is not capped at 2^48-1 (affects §4.4 BendBV)

S1 states that `Nat` literals past `256n` are `U32.to_nat(n)` underneath and cap at `4294967295n`.

**Consequence:** BendBV cannot be "a `Nat` constrained below `2^w`" as §4.4 assumed. The primitive layer is `U32` with an explicit `mask(w)`, because `U32` is also the only released type carrying `and or xor not shl shr`. Widths above 32 are out of scope for v1 rather than "handled symbolically" by a `Nat` encoding nobody has written.

### 2. `--verdict` exists and is the stronger check — but is reported broken on 2.0.39

S1 documents `bend PROOF.bend --verdict` as rechecking with a small kernel that has a proof in Lean, exporting the translation with `-o PROOF.bendtt`.

S6 reports that on 2.0.39, `--verdict` exits 1 with `parse error: expected '1'` and a TypeScript-vs-kernel mismatch diagnostic — including for the minimal `{0n == 0n : Nat}`.

**Consequence:** the A5 ablation and the D5 trust-integrity rule (`CDC = 0`) both assumed a working second checker. Phase 0 must record `verdict_available` for the pinned release. If it is false, A5 leaves the confirmatory set, `CDC` is reported as not measurable, and D5 falls back to canary false-accepts under the default checker plus an independent evaluator. No result may describe a proof as kernel-validated.

### 3. There is a verified execution path for the reference model (affects L1/L2)

S1 documents `bend model.bend -o model.mjs`, an ES module of the non-IO defs, with constructors as `{$: "Name", field: value}` and `Nat` as a JS number.

**Consequence:** the "Bend cannot be executed conveniently from scripts" risk in §13 is retired for the vector-comparison path. `bend_vectors` → `model.mjs` under Node → cocotb comparison is the L1/L2 route, with `bend model.bend` (normalised `main`) kept only for tiny sanity inputs.

## Verified as written

- The laws/proofs convention: `LAWS.bend` holds claims, `PROOF.bend` fills them with same-named defs, `bend PROOF.bend` prints `SOME PROOFS FAIL` / `ALL PROOFS CHECK`, and a `PROOF.bend` beside a `LAWS.bend` must import it.
- No tactics and no proof search; `?name` prints the goal and `?TODO` leaves it open; `%e : P` rewrites.
- Law parameters: `for x: A`, `for +x: A`, and `for y: B where P(y)` which binds the value and its proof; `exs z: C` requires a witness — directly useful for the non-vacuity requirement.
- No `if` syntax (use `match` on `True{}`/`False{}`), no mutual recursion, termination mandatory, `@unsafe` escapes the proof discipline.
- A law left open in one file may be filled as `def M.name(..)` in another — so one `LAWS.bend` can be discharged by several independent proof attempts.
- `--check-only` checks a file and its imports without running anything.

## Left unresolved on purpose

| Claim | Why unresolved | Handling |
|---|---|---|
| "Compiler is 99% AI-written and not audited" | Not verifiable from repository contents | Keep the canary suite as the operative defence; describe as reported |
| Platform support (no Windows build) | Must be measured at image build | Container-only pipeline; assert nothing about native Windows |
| `bend2-lsp` editor server | Not needed by Phase 0 | Editor extension stays out of scope until verified |
| Release cadence / version churn | Time-dependent | Pin by release + commit at Phase 0 exit (Q-1) |

## What Phase 0 must now do differently

1. **0.3a** — prove the `model.mjs` + Node vector path end to end on one toy model.
2. **0.5a** — record `verdict_available` for the pinned release and attach the exact failing command if false.
3. **0.4** — build BendBV on `U32` + `mask(w)`; do not attempt a `Nat` encoding.
4. **0.8** — add lint rule **L015** (provenance sidecar present and hash-matching).

These are tracked as issues on the project board, not as prose promises.
