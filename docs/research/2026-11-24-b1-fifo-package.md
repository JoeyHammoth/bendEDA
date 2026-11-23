# B1 FIFO: the first task package, as a draft

**Question.** Can the repository carry a complete task package — spec, model,
laws, manifest, abstraction map, reference proofs, SVA, provenance — whose laws
are all closed by the pinned checker, and what does that exercise expose?

**Answer.** Yes for LA1, LA2 and LA8: 19 laws are closed by the composed book and
`law lint` reports zero findings. LA3 is now *measured* and **fails**: 32 mutants,
28 killed, kill rate 0.875 against a 0.9 bar. The failure is informative — one law
is type-enforced, and one survived only because the mutant budget truncates in
source order. Everything that needs a second role (RPA proofs, PA's C2, OAA's
oracle) or an EDA toolchain is still open and is named in the package README.

## What was run

Pinned checker: Bend 2.0.40 at `624dd9f`, sources under `.bend-cache/`.

```console
$ cat tasks/seq/B1_fifo/model.bend tasks/seq/B1_fifo/LAWS.bend \
      tasks/seq/B1_fifo/PROOF_ref.bend > .bend-cache/b1/book.bend
$ bun .bend-cache/bend-2.0.40/bend2/main.ts .bend-cache/b1/book.bend
ALL PROOFS CHECK
Use --verdict for mathematical validity.

$ python -m bendeda law lint tasks/seq/B1_fifo
tasks\seq\B1_fifo: 19 law(s), 0 finding(s)
law lint: 1 package(s), 19 law(s), 0 finding(s)

$ python -m unittest tests.test_b1_fifo -v
Ran 10 tests
OK

$ cat tasks/seq/B1_fifo/LAWS.bend tasks/seq/B1_fifo/PROOF_ref.bend > /tmp/laws.bend
$ python -m bendeda law mutate tasks/seq/B1_fifo/model.bend --laws /tmp/laws.bend \
      --local --max-mutants 32 --out .bend-cache/b1/mutation32.json
law mutate: 32 mutant(s), 28 killed by at least one law, kill rate 0.875,
            2 law(s) survived every mutant
$ echo $?
1

$ python -m bendeda law lint tasks/seq/B1_fifo --mutation .bend-cache/b1/mutation32.json
tasks\seq\B1_fifo: 19 law(s), 2 finding(s)
  L006  [fifo_s01_count_within_depth]: law survived all 32 model mutants, so it does not constrain the model
  L006  [fifo_f12_idle_preserves_head]: law survived all 32 model mutants, so it does not constrain the model
```

The negative control is refused as required:

```console
$ cat tasks/seq/B1_fifo/model.bend \
      tasks/seq/B1_fifo/negative/fifo_n01_strict_below_depth.bend > /tmp/neg.bend
$ bun ... /tmp/neg.bend
SOME PROOFS FAIL
Error:
- expected : True{}
- observed : False{}
Location: fifo_n01_strict_below_depth
```

## Findings

**1. The first LA3 run measured nothing, because the catalogue knew no table.**
The original catalogue swapped arithmetic operators and bumped literals on
arithmetic lines. The B1 model is a finite transition table and has neither, so
`law mutate` reported `0 mutant(s)` and exit 3 — a correct refusal, and a gate that
could never apply to the model shape the specification work produces. The
catalogue now exchanges the bodies of sibling `match` arms with identical bound
names and replaces a nullary constructor with another of its declared type. Both
edits keep the program well typed, so a survivor means "no law noticed".

The same run exposed a second defect: `LAWS.bend` holds laws only, and a law with
no proof also prints `SOME PROOFS FAIL` (`1 TODO found`). Counting that as a kill
would credit the catalogue with catching a bug it never saw, so the tool now
records it as an error. The gate has to be given the composed law+proof file.

**2. LA3 fails at 0.875, and the two survivors have different causes.**

```console
$ bun ... .bend-cache/b1/book_idle.bend     # Full arm: idle treated as pop
SOME PROOFS FAIL
- expected : b
- observed : a
```

- `fifo_s01_count_within_depth` is **type-enforced**: `count` decodes a
  three-valued `Level`, so `count <= 2` cannot be false for any inhabitant, and no
  branch or constructor mutant can produce a count of 3. It is not vacuous as a
  statement — a `count` whose `Full` decodes to `3n` is refuted with
  `expected False{} / observed True{}` — but the type excludes the states that
  would refute it. L006 firing here is correct, and the law needs either dropping
  from the reduced instance or restating parametrically.
- `fifo_f12_idle_preserves_head` survived because `--max-mutants 32` truncates in
  source order and stops inside the `Half` arm of `step`. The hand-written Full-arm
  mutant above is refuted, so the survivor is a budget artifact, not a weak law.
  A 48-mutant run costs roughly 40 minutes locally (each mutant is 19 checker
  invocations, ~50 s per mutant), and the cap is recorded with the result.

**3. A Nat occupancy cannot be bounded, and the induction lands on the wrong bound.**
The next step after this package was a depth-parameterised model. Reducing it to
D = 2 with the occupancy as a `Nat` shows why the finite `Level` is not merely
convenient — the law is *false* over the type, because `MkFifo{a, b, n}` admits
`n = 5`:

```console
$ bun main.ts .bend-cache/scratch/fifo_nat_probe.bend
SOME PROOFS FAIL
Error:
- expected : Cmp.is_le(Nat.cmp(count(s), 2n))
- observed : True{}
Context:
- s : Fifo
Location: fifo_nat_s01_count_within_depth
```

Recursing on the occupancy, as cookbook S3 does, does not fix it: the hypothesis
it produces is about a *different* bound, because the structural descent lowers the
argument while the law's literal stays at 2.

```console
$ bun main.ts .bend-cache/scratch/fifo_nat_induction_probe.bend
SOME PROOFS FAIL
Error:
- expected : {Cmp.is_le(Nat.cmp(p, 1n)) == True{} : Bool}
- observed : {Cmp.is_le(Nat.cmp(p, 2n)) == True{} : Bool}
Context:
- a : U32
- b : U32
- p : Nat
Location: fifo_s01_count_within_depth
```

So a parametric model needs the bound in the type (a length-indexed vector, or a
proof field) or a reachable-state invariant plus `le`-monotonicity lemmas — a lemma
library the pin does not ship. That is a research task, not a one-session edit, and
the reduced ADT stays the only shape whose laws close by evaluation.

## What the package cannot claim

- `PROOF_ref.bend` is correct but not independent: the same session wrote the
  laws and the proofs.
- `props_c2.sv` was written in the same session, after the laws. Parity between
  LC(C2) and LC(C3) from these two files would be confounded (LA6).
- Neither SVA pack has been elaborated: no SystemVerilog toolchain is installed
  locally and the OSS CAD image was not asked to run one.
- No oracle pack exists, so no sealed commitment is recorded and no seeded bug
  corpus exists for LA4/LA5.
- LA3 has no passing result: 0.875 against a 0.9 bar, with one survivor that is a
  cap artifact and one that the type makes unfalsifiable.
- The package is `draft`. `locked/LOCKED.json` remains empty and
  `provenance.yaml` says `locked.by: unlocked` rather than naming a Conductor.
