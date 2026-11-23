# Checker canary calibration, Bend 2.0.40

**Issue:** [#9](https://github.com/JoeyHammoth/bendEDA/issues/9), Appendix K R-05 and G-02.
**Run:** 2026-11-23, Bend 2.0.40, `bendeda canary --local` (pinned sources under Bun 1.4.5)
and `bendeda canary --image pinned` (the released binary in `bendeda/bend:2.0.40`).

## What this measures, and what it does not

The canary suite asks one question: does the checker accept anything it must
refuse? Thirty-two negative controls state false or unproved claims across eight
families; four positive controls state true claims, because a checker that
refused everything would pass a negative-only suite.

A control is only evidence if the refusal happens at the **law layer** — where
the checker compared the two sides of the equation and disagreed. Bend 2.0.40
prints `SOME PROOFS FAIL` for a false theorem, a typo, a TODO and a parse error
alike, so the runner classifies the refusal from the error text and fails the
suite when a control is refused somewhere else. That rule is not pedantry: of
the 32 controls, 18 reach the law layer; the other 14 are refused by name,
order, type, termination and TODO rules. A suite of 32 files that all failed to
parse would report "0 false accepts" and mean nothing.

Rungs, from the runner (first match wins):

| Stage | Meaning |
|---|---|
| `law` | the checker compared expected and observed values — the equation itself was judged false |
| `undefined` | a called name does not exist |
| `order` | the name exists but is used before it is implemented (defs are checked in file order) |
| `type` | a term or claim has the wrong type |
| `termination` | the proof develops a call that is not smaller |
| `todo` | a law has no proof at all |
| `front-end` | anything else: no law verdict was reached |

## The controls

Generated from the same catalog the CI runs, so this table cannot drift from the
suite without the note being regenerated.

| Control | Family | Claim under test | Refused at |
|---|---|---|---|
| `a01` | arithmetic | addition is off by one | `law` |
| `a02` | arithmetic | subtraction returns the wrong difference | `law` |
| `a03` | arithmetic | multiplication is off by one | `law` |
| `a04` | arithmetic | a shift by four is claimed to give fifteen | `law` |
| `a05` | arithmetic | a width-truncated sum claimed as a 32-bit sum | `law` |
| `a06` | arithmetic | underflow claimed as a positive difference | `law` |
| `a07` | arithmetic | a shift wider than the word is claimed to shift | `law` |
| `a08` | arithmetic | square is off by one | `law` |
| `u01` | universal | addition claimed equal to multiplication | `law` |
| `u02` | universal | adding one claimed to change nothing | `law` |
| `u03` | universal | conjunction claimed equal to disjunction | `law` |
| `u04` | universal | subtraction claimed to commute | `law` |
| `u05` | universal | bitwise and claimed to absorb without a hypothesis | `law` |
| `u06` | universal | double negation claimed to be negation | `law` |
| `u07` | universal | addition claimed equal to subtraction | `law` |
| `i01` | incomplete | a true universal law left to reflexivity | `law` |
| `i02` | incomplete | the proof body evaluates instead of proving | `type` |
| `i03` | incomplete | a case split that decides one branch wrongly | `law` |
| `m01` | missing | a proof calls a lemma that does not exist | `undefined` |
| `m02` | missing | a Base lemma is called under a name Base does not have | `undefined` |
| `m03` | missing | a proof calls a lemma defined after it in the same file | `order` |
| `ty01` | type | a Bool equation is claimed to be Nat | `type` |
| `ty02` | type | a Nat parameter is used as a word | `type` |
| `ty03` | type | a lemma is applied to the wrong word width | `type` |
| `tm01` | termination | a proof is defined in terms of itself, unchanged | `termination` |
| `tm02` | termination | recursion develops a larger argument | `termination` |
| `ax01` | axiom | a law with no proof is used as if it were an axiom | `order` |
| `ax02` | axiom | an invented helper law is itself false | `law` |
| `ax03` | axiom | the goal is restated as a binding instead of proved | `type` |
| `ax04` | axiom | a false law is left with no proof at all | `todo` |
| `s01` | shape | the proof takes fewer arguments than the law | `type` |
| `s02` | shape | a proof is filed under a name that no law claims | `type` |
| `p01` | positive | a tautology is accepted, so refusal is not blanket | `*accept*` |
| `p02` | positive | an unused hypothesis does not make a proof fail | `*accept*` |
| `p03` | positive | a genuine case split is accepted | `*accept*` |
| `p04` | positive | the true 32-bit sum is accepted, so a05 is about the value | `*accept*` |

36 controls: 32 negative, 4 positive; 18 refusals at the law layer; 0 false accepts.

## Result

```
canary: 32 negative controls run, 0 false accepts, 0 false rejects,
        0 refused at the wrong stage, 0 unavailable, 18 refused at the law layer
```

Exit code 0. No false accept was found, so nothing needed reporting upstream and
the Bend arms are not halted. If one appears, `bendeda canary` exits 1 and both
CI jobs fail: a false accept is not a warning in this programme.

## What calibration caught — in the controls, not the checker

The first run reported two false accepts and one false reject. All three were
mistakes in my controls, and they are worth recording because each is a way a
canary suite can quietly become evidence of nothing:

- **`U32.add(200, 100) == 300` was accepted because it is true.** 300 fits in 32
  bits. The truncated-sum bug only appears at a narrower width, which is why the
  BendBV control needs `mask(8n, ...)`. The control now claims the 8-bit answer
  (`44`) at 32 bits, and a positive control claims `300`, so the pair differs
  only in the value.
- **`U32.shln(1, 4)` inside a claim typed `: U32` was a type error, not a false
  law.** The literal `4` was read as a `U32` where a `Nat` shift amount belongs;
  `4n` fixes it. The control had been "passing" for the wrong reason.
- **`U32.add_comm` exists in Base.** My "missing lemma" control called a real
  lemma and proved a true law, so it was accepted — correctly. It now calls
  `Word.add_assoc`, which Base does not have.

Two language rules also became explicit controls rather than folklore: a `def`
with no return type must fill a law of that name (so a helper that fills nothing
is a front-end error), and a law used before its own proof appears is refused by
the file-order rule, not by an unknown-name rule.

## `verdict_available`: false at this pin, with evidence

G-02 needs to know whether the proven-kernel checker works at the pinned
release. Bend 2.0.40 has the flag — `bend <file> --verdict` — but it needs a
Lean toolchain and a built BendTT kernel, and neither is present here or in the
pinned image. Exact command and output:

```
$ python -m bendeda canary --local --verdict --only p01
Error: BendTT infrastructure: the kernel did not build (lean: Executable not
found in $PATH: "lean"); --verdict needs Lean v4.34.0 (elan toolchain
leanprover/lean4:v4.34.0), or $BENDTT set to a built kernel
```

Exit code 3 — nothing was measured, which the gate reports as neither pass nor
fail. `docker/Dockerfile.bend` installs `ca-certificates` and `curl` only, so
the released binary in the pinned image reports the same thing; CI records it
with `--verdict --only a01` and does not fail the build on it, because the
absence is the finding.

**Consequence (G-02, recorded in `docker/versions.lock`):** ablation A5 leaves
the confirmatory set, `CDC` is reported not measurable, and D5's `CDC = 0`
clause is replaced by default-checker canary false-accepts plus an independent
evaluator that recomputes each law on enumerated reduced domains. No result may
describe a proof as kernel-validated.

Making it available would mean adding Lean v4.34.0 and building BendTT inside
the Bend image, which changes the image digest and the trust base. That is a
Phase 0 decision this issue did not take; it is logged as a possible follow-up
rather than smuggled into the pin.

## Limits

- **The suite bounds one failure mode.** It shows that this checker rejects these
  32 claims. It cannot show that a claim outside the catalog is false; that
  remains the independent evaluator's job (D5 fallback).
- **A vacuous law is accepted, correctly.** `p02` proves that a law with an
  unused hypothesis passes — the checker judges the proposition, not its
  usefulness. Vacuity and traceability are `law lint`'s rules (#10), not the
  canary's.
- **Timing is not measured.** Appendix K watches proof effort against the token
  budget; this suite records verdicts only.

## Reproduce

```bash
python tools/fetch_bend.py
BENDEDA_BUN=bun BENDEDA_BEND_CLI=.bend-cache/bend-2.0.40/bend2/main.ts \
  python -m bendeda canary --local --out .bend-cache/canary.json
```

CI runs the same catalog twice: `vector-path` through the pinned sources under
Bun, `bend-image` through the released binary inside the pinned image. A
checker that behaves differently in the two is itself a finding.
