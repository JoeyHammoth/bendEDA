# The proof cookbook

This is the guide the agent is given before it writes a proof (Appendix H.11,
Phase 0.8a). It is written for one checker, Bend 2.0.40 at commit `624dd9f`, and
every example in it is run by `tests/test_cookbook.py` against that checker. When
the version changes, the examples are re-run before this document is reused; the
hash of `docs/cookbook/` is recorded at the Phase 3 freeze.

Two rules shape everything here:

* **The checker is the authority.** A law is proved when `bend` prints
  `ALL PROOFS CHECK` for the file that contains it. Reasoning that convinces a
  reader and not the checker counts as nothing.
* **No escape hatches.** A proof that uses any construct in the PEH list below is
  not closed, whatever it prints. The list is enumerated in
  [`bendeda/laws/peh.py`](../bendeda/laws/peh.py) and rule L007 enforces it.

## How to run an example

```bash
python tools/fetch_bend.py
BENDEDA_BUN=bun BENDEDA_BEND_CLI=.bend-cache/bend-2.0.40/bend2/main.ts \
  bun .bend-cache/bend-2.0.40/bend2/main.ts docs/cookbook/s1_direct.bend
```

or, in the image, `bend docs/cookbook/s1_direct.bend`. Every file in
`docs/cookbook/` is a complete book: it imports `Base`, states its laws and
proves them, so it checks identically from any working directory.

## Syntax that matters

A **book** is an optional `import Base` (or `import <path> as <Name>`) followed by
laws, definitions and types. There is no inference: every argument is given
explicitly, and implicit arguments must be named when the checker cannot guess
them.

```bend
law name:
  for a: U32                 # a clause, one per parameter
  for h : {a == a : U32}     # a proposition hypothesis
  {claim == claim : U32}     # the claim, with its type

def name(a, h):              # the proof: same name, bare parameters, no types
  <term>
```

A **closed** law has no `for` clauses; its proof is still a `def` with the same
name and an empty parameter list.

```bend
law cook_s1_and_eval:
  {U32.and(12, 10) == 8 : U32}

def cook_s1_and_eval():
  {==}
```

`{==}` is the reflexive close: it succeeds only when both sides reduce to the
same value. It is not a tactic that searches; if the goal is not already
reflexive, it fails.

**Term building.** Equality is intensional. `Equal.cong(A, B, f, x, y, eq)`
lifts `x == y` through `f`; `Equal.trans(A, x, y, z, xy, yz)` chains two
equalities. `Equal.refl` closes a goal the checker will not close by itself.

**Case analysis** is `match` on a value, one branch per constructor. Branches must
be exhaustive; a missing constructor is a refusal, not a warning.

**Affinity.** A binding is used once unless it is introduced with `+`: `match a:
case WCon{+h, +t}` lets `h` and `t` be read twice, and `+ww = w` aliases a
parameter that the proof needs more than once. This is not in the guide; it is
what Base's own proofs do, and a proof that ignores it fails with
`consumed more than once`.

**Literals.** `4` is a `U32`; `4n` is a `Nat`. `U32.shln` takes its shift as a
`Nat`, so `U32.shln(1, 4n)` is well typed and `U32.shln(1, 4)` is not.

**Nat recursion.** `match n:` gives `0n` and `1n+p`; the recursive call on `p` is
the induction hypothesis. There is no separate induction tactic.

## The nine strategies

Each strategy has a file, and each law in it is a worked example. None of these
is a reference proof of a task law: they are generic lemmas about Booleans,
words and a three-state machine, and a task's laws are never shaped like
`cook_*`.

| Strategy | File | What it demonstrates |
|---|---|---|
| **S1** direct computation | `s1_direct.bend` | closed goals that reduce by evaluation, including U32 wrap |
| **S2** case analysis | `s2_case.bend` | splitting on `Bool`, two exhaustive branches |
| **S3** induction | `s3_induction.bend` | `match` on `Nat` with a recursive hypothesis; rebuilding a `WCon` |
| **S4** inductive invariant | `s4_invariant.bend` | a predicate at reset and closed under `step`, with the hypothesis discharging the bad branch |
| **S5** rewriting with lemmas | `s5_rewrite.bend` | `Equal.cong` into a context, then `Equal.trans` to chain |
| **S6** lemma factoring | `s6_factoring.bend` | one `aux_` lemma, two laws that rewrite with it |
| **S7** refinement relation | `s7_refinement.bend` | a relation carried as a hypothesis and preserved through an output function |
| **S8** bounded unrolling | `s8_unroll.bend` | `run(2n, s)` unfolded to two steps and closed by a lemma |
| **S9** counterexample | `s9_counterexample.bend` | the one file that must be refused, with both values printed |

### S1 — make the goal reflexive

Four closed laws: `U32.and(12, 10) == 8`, `U32.shln(1, 4n) == 16`,
`U32.add(4294967295, 1) == 0`, `Nat.add(2n, 3n) == 5n`. The last two are the ones
worth reading: U32 addition wraps at 2^32, and a Nat literal with an `n` suffix is
a different type from the same digits without it. If `{==}` fails on a closed
goal, the claim is false or a name is misspelled; there is nothing to prove.

### S2 — split, then reduce

`cook_s2_and_true`, `cook_s2_or_false`, `cook_s2_not_not`: each is `match a` with
`False{}` and `True{}` branches. After the split both sides reduce, so each branch
is `{==}`. A law over a `Bool` that needs more than this is usually a law whose
statement is wrong.

### S3 — induction is a recursive call

`cook_s3_bool_and_idem` is the base case of the pattern; `cook_s3_word_and_idem`
uses it. The step case rebuilds `WCon{...}`, so the goal compares two constructed
words. `Equal.cong` lifts the head hypothesis and the tail hypothesis separately,
and `Equal.trans` puts them together. The step case is where the `+` bindings
appear: `Word.and(p, t, t)` reads `t` twice.

### S4 — the invariant is a hypothesis

`cook_s4_init` is `{==}`. `cook_s4_step` carries `h : {cook_live(m) == True{}}` and
splits on the three states. Two branches reduce to `True{} == True{}`. The third
branch, `Fired{}`, reduces to `False{} == True{}` — exactly `h`, so the proof term
is `h` and the branch is provable *because the hypothesis forbids it*. This is
the whole content of an inductive invariant; a version without the hypothesis
fails on `Fired{}`, which is what the harness wants to see.

### S5 — rewriting is directional

`cook_s5_absorb` has the goal `Word.and(n, Word.and(n, a, a), b) == Word.and(n, a, b)`
and the lemma `cook_s5_word_and_idem : Word.and(n, a, a) == a`. `Equal.cong` with
`t => Word.and(n, t, b)` rewrites the left occurrence. `cook_s5_absorb_nested`
then rewrites inside a larger context with the result, which is the chaining
`Equal.trans` would express in one term. If a rewrite does not apply, check the
direction: the lemma's left side must be the subterm in the goal.

### S6 — factor the repeated goal

`aux_cook_s6_word_and_self` is stated generally and used by `cook_s6_use_left`
and `cook_s6_use_right`. The `aux_` prefix is required by the harness, and a
lemma that only holds for the value you needed is a proof of the example, not of
the law.

### S7 — carry the relation

`cook_s7_flip` takes `h : {a == b : Bool}` and concludes
`Bool.not(a) == Bool.not(b)`. The proof is one `Equal.cong` through the output
function. A real refinement law replaces `Bool.not` with the model's step and the
relation with a predicate over both states; the shape — relation in, congruence
out — does not change.

### S8 — unroll only while k is small

`cook_s8_run(2n, s)` reduces to `Bool.not(Bool.not(s))` because `2n` is a literal.
`cook_s8_two_steps` closes it with `cook_s8_not_not`. Unrolling a symbolic `k`
does not work: once `k` is a variable the recursion is stuck, and the law needs
induction (S3) instead. S8 is for laws that name a small `k` in the statement.

### S9 — report the counterexample

`s9_counterexample.bend` claims `U32.add(4294967295, 1) == 4294967295` and is
refused:

```text
SOME PROOFS FAIL
Error:
- expected : 0
- observed : 4294967295
Location: cook_s9_bad_wrap
Note: the left side of the equality is the expected, the right side is the observed.
```

A false law is a finding about the law or the model, not a proof obligation. The
report should carry the inputs, the observed value and the expected one — the
checker already prints the last two.

## Diagnostics and what they mean

These are real outputs from the pin, not paraphrases. The first line is the
message to search for.

| Diagnostic | Cause | Fix |
|---|---|---|
| `expected : Nat` / `observed : U32` | a literal without `n` used where a `Nat` is required | write `4n`; the checker has no numeric coercion |
| `expected : a defined name` | a lemma or definition used before it appears in the file | move the `def` above the use; Bend checks in file order |
| `SOME PROOFS FAIL` with `expected`/`observed` | the claim is false for the model | record the counterexample; do not edit the law |
| `TODO found` | a `?TODO` hole was reached | finish the proof; this is PEH-03 |
| `a call smaller than` | recursion does not descend on a strict subterm | restructure the induction |
| `consumed more than once` | an affine binding was read twice | bind with `+`, as in `case WCon{+h, +t}` |
| `checked in file order` | a proof refers to a law defined below it | reorder, or inline the needed proof |
| `expected : ':'` / `observed : 'd'` | a `type` declaration is missing its `is Data:` form | write `type T is Data:` before the constructors |
| `left side of the equality is the expected` | the checker compared two values: the refusal is about the law | read both values before changing anything |

The last row matters: a refusal without that note was not a comparison of two
values, so it says nothing about the law. The canary suite (`bendeda canary`)
scores exactly this distinction, and a proof report that conflates the two is
wrong in the same way.

## The PEH list

The enumerated proof escape hatches, with the id that L007 reports. A file that
contains one is not closed.

| Id | Construct | Why it is an escape hatch | Instead |
|---|---|---|---|
| **PEH-01** | `@unsafe` | the definition opts out of the wall: self-calls skip the descent check and it may call an unfilled law | prove the descent |
| **PEH-02** | `def f?(..)` | the grammar defines it as `@unsafe def f(..)` | write `def f(..)` |
| **PEH-03** | `?TODO` | checks at any goal and marks the book incomplete | fill the goal |
| **PEH-04** | `?name` | a named hole fails every check and is shown against the goal | write the term |
| **PEH-05** | a foreign body (`import "..."` inside a `def`) | the body is a promise the checker reads as given | implement it in Bend |
| **PEH-06** | `Array.fork`, `Array.join`, `Array.get_unchecked` | these Base definitions are themselves `@unsafe` at the pin | use the safe API |
| **PEH-07** | a `TODO` marker | the checker ignores comments, so the file checks while the work is unfinished | finish it, or move it to an issue |

PEH-06 is the entry most likely to be missed, because it looks like an ordinary
Base call. PEH-07 is the least severe and still counts: "proved with a TODO in
the file" is a statement about a draft.

## What this cookbook is not

- It is not a reference proof of any task law. The examples are `cook_*` and
  `aux_cook_*` and a test refuses any example that looks like a task law or
  mentions `tasks/`.
- It is not complete. A law outside the shapes above (mutual recursion,
  array-heavy state, nested data with several parameters) may need a proof this
  guide does not show. The escalation ladder is: re-read the definitions, add an
  `aux_` lemma, strengthen the invariant, try another strategy, stop and report.
- It is not a substitute for the checker. Every statement here was validated by
  running the files; a future version bump re-runs them or this document is stale.
