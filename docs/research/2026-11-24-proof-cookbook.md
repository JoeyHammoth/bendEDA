# The proof cookbook and the PEH list

Issue #11, Phase 0.8a. Appendix H.11 asks for 20-30 worked examples across
strategies S1-S9, a syntax section validated against the pinned checker, a
diagnostics table, and an enumerated proof escape-hatch (PEH) list that lint rule
L007 consumes. The prose is `docs/proof_cookbook.md`; the examples are
`docs/cookbook/`; the PEH list is `bendeda/laws/peh.py`.

The rule that shaped the build: an example that does not check is not an
example. Every file is compiled by `tests/test_cookbook.py` through Bend 2.0.40
at commit `624dd9f`, and the one file that is *supposed* to fail is asserted to
fail with both values printed.

## What checks

| File | Strategy | Laws | Result |
|---|---|---|---|
| `s1_direct.bend` | S1 direct computation | 4 | `ALL PROOFS CHECK` |
| `s2_case.bend` | S2 case analysis | 3 | `ALL PROOFS CHECK` |
| `s3_induction.bend` | S3 induction | 2 | `ALL PROOFS CHECK` |
| `s4_invariant.bend` | S4 inductive invariant | 2 | `ALL PROOFS CHECK` |
| `s5_rewrite.bend` | S5 rewriting with lemmas | 4 | `ALL PROOFS CHECK` |
| `s6_factoring.bend` | S6 lemma factoring | 4 | `ALL PROOFS CHECK` |
| `s7_refinement.bend` | S7 refinement relation | 1 | `ALL PROOFS CHECK` |
| `s8_unroll.bend` | S8 bounded unrolling | 2 | `ALL PROOFS CHECK` |
| `s9_counterexample.bend` | S9 counterexample report | 1 | `SOME PROOFS FAIL` **by design** |

23 laws in total, inside the 20-30 range Appendix H.11 sets. S9's refusal is the
only expected one:

```text
$ bend docs/cookbook/s9_counterexample.bend
SOME PROOFS FAIL
Error:
- expected : 0
- observed : 4294967295
Location: cook_s9_bad_wrap
Note: the left side of the equality is the expected, the right side is the observed.
```

Two mistakes were found by running the examples rather than by reading them, and
both are in the cookbook as diagnostics:

- `U32.shln(1, 4)` is ill typed — the shift is a `Nat` — and the checker says
  `expected : Nat / observed : U32`. `U32.shln(1, 4n)` is the fix.
- `type T is A{} | B{}` is not the pin's ADT syntax; it is `type T is Data:`
  followed by one constructor per line. The parser reports `expected ':'`.

The S4 example was also wrong on the first attempt for a substantive reason: the
machine moved `Armed{}` to a state the invariant calls dead, and the checker
refused the `Armed{}` branch with `expected : False{} / observed : True{}` while
the hypothesis was `True{} == True{}`. The invariant had to be *true*, not merely
stated. That is the most useful example in the set, because it is the failure
mode an agent will actually produce.

## The PEH list

`bendeda/laws/peh.py` enumerates seven entries. Each has an id, a regex, why it
bypasses the checker, and what to do instead; L007 reports the id, so a report
can be counted (`PEH-05 x2`) rather than summarised.

| Id | Construct | Grounded in |
|---|---|---|
| PEH-01 | `@unsafe` | `bend.ts`: an unsafe def's self-calls skip descent, its binder domains form `+` at any kind, and it may call an unfilled law |
| PEH-02 | `def f?(..)` | `bend.ts` grammar: `"def f?(..)" is "@unsafe def f(..)"` |
| PEH-03 | `?TODO` | `bend.ts`: checks at any goal and marks the book incomplete |
| PEH-04 | `?name` | `bend.ts`: a hole fails every check and is shown against the goal |
| PEH-05 | foreign body (`import "..."` inside a `def`) | `bend.ts` grammar: a `Def` body may be an import list; the body is a promise |
| PEH-06 | `Array.fork`, `Array.join`, `Array.get_unchecked` | `base.bend`: these three carry `@unsafe` at the pin |
| PEH-07 | a `TODO` marker | the checker ignores comments, so an unfinished file still checks |

Ordering is deliberate: PEH-03 is tested before PEH-04 (whose pattern excludes
`?TODO`), and PEH-07's pattern excludes a preceding `?` so `?TODO` is not counted
twice. Comment lines are skipped — the cookbook discusses these constructs in
prose, and a scanner that flagged its own documentation would be turned off.

The old tuple in `rules.py` held four patterns and described itself as a Phase 0
subset. It is gone; `ESCAPE_HATCHES` no longer exists, and `peh.PEH` is the single
source.

## Evidence

```console
$ python -m unittest tests.test_cookbook -v
test_each_construct_is_recognised ... ok
test_a_todo_hole_is_not_double_counted_as_a_marker ... ok
test_comments_are_not_hits ... ok
test_l007_names_the_entry ... ok
test_every_example_file_is_listed_and_holds_the_expected_laws ... ok
test_examples_check_and_the_counterexample_is_refused ... ok
...
Ran 9 tests in 13.7s
OK
```

The test asserts the *set* of files, their law counts, the total (20-30), that
every law is named `cook_*` or `aux_*`, that no file mentions `tasks/`, and that
the prose documents every file, every strategy and every PEH id. A cookbook that
lost an example, or a PEH entry that lost its doc, fails rather than drifting.

## Hashes at the time of writing

Not the Phase 3 freeze hash — that tag does not exist yet — but recorded so a
later re-validation can tell whether a file changed:

```text
e14eefedd370943fb845760374632abb2c6f485969381f570abca8e087e7341c  s1_direct.bend
5b9d09028bcb4d448618825a79c7fc04bec377ea4e79ceeb9127d8df62740292  s2_case.bend
54c52e6c88451d9979062933a68a2707ce7d196d913429ee8b19326774e1d2a2  s3_induction.bend
380d40d9bfbb2dc630f276a5fa43b0a81f56b2b0c1e4712a7c425f4a2479cce2  s4_invariant.bend
cf65318a00a0d1a48cfc2d1a64ff7d1ed63264bbdd23a9546ac148ecf3002fe5  s5_rewrite.bend
b92b5d5e9b2e4a9da3b9c13706e5b9f0d8dd5a7bed0574eb53d863c7575ae531  s6_factoring.bend
e94f4b662a843376b4acc84861eb2c7df8925b34ec4834df7ef8cdddc8082fb9  s7_refinement.bend
45561cf53d3f9517f0059855f2a2cb78cabc6ebe388eec1fbb903c3ae74b1276  s8_unroll.bend
dd7d548bfd6a99d4bc65dd6cd353fd3c691cef7c52e11f77611243beb2d5322b  s9_counterexample.bend
0e34098a60e02a17b46069285518dd00fe50cc69383aaa6d27379e433a3c6c7c  ../../docs/proof_cookbook.md
e2d0bdecb22a758124c90372e3e3cd9c166242fa2a5db383bde39c602c98df2a  directory digest (concatenated files, sorted)
```

## Limits

- The examples are generic by construction, but "generic" is a judgement. A test
  enforces the naming and the absence of `tasks/`; it cannot prove that no future
  task law will resemble `cook_s4_step`.
- S4's hypothesis is unused in two of its three branches. The pin permits that
  (bindings are affine, not linear), so the branch that *needs* the hypothesis is
  the evidence that it matters. A checker with stricter linearity would reject
  this file.
- The cookbook covers what the pin can express today. Mutual recursion, arrays
  with several indices and nested data with dependent fields are not represented;
  the escalation ladder in the prose says so rather than pretending otherwise.
- The hash above is a record, not a lock. `locked/` stays empty until the freeze.
