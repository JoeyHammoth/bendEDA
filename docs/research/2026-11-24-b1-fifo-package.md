# B1 FIFO: the first task package, as a draft

**Question.** Can the repository carry a complete task package — spec, model,
laws, manifest, abstraction map, reference proofs, SVA, provenance — whose laws
are all closed by the pinned checker, and what does that exercise expose?

**Answer.** Yes for LA1, LA2 and LA8: 22 laws are closed by the composed book and
`law lint` reports zero findings. LA3 is *measured* over the whole catalogue and now
**passes**: 51 mutants, 51 killed, kill rate 1.00 against a 0.9 bar. Getting there
was the finding — the same catalogue failed at 0.804 against the first law set,
because the laws pinned the data (`head`, and `count` as a state predicate) and never
the occupancy a cycle produces; three post-state laws close that gap. Everything that
needs a second role (RPA proofs, PA's C2, OAA's oracle) or an EDA toolchain is still
open and is named in the package README.

## What was run

Pinned checker: Bend 2.0.40 at `624dd9f`, sources under `.bend-cache/`.

```console
$ cat tasks/seq/B1_fifo/model.bend tasks/seq/B1_fifo/LAWS.bend \
      tasks/seq/B1_fifo/PROOF_ref.bend > .bend-cache/b1/book.bend
$ bun .bend-cache/bend-2.0.40/bend2/main.ts .bend-cache/b1/book.bend
ALL PROOFS CHECK
Use --verdict for mathematical validity.

$ python -m bendeda law lint tasks/seq/B1_fifo
tasks\seq\B1_fifo: 22 law(s), 0 finding(s)
law lint: 1 package(s), 22 law(s), 0 finding(s)

$ python -m unittest tests.test_b1_fifo -v
Ran 10 tests
OK

$ cat tasks/seq/B1_fifo/LAWS.bend tasks/seq/B1_fifo/PROOF_ref.bend > /tmp/laws.bend
$ python -m bendeda law mutate tasks/seq/B1_fifo/model.bend --laws /tmp/laws.bend \
      --local --max-mutants 60 --out .bend-cache/b1/mutation_full.json
law mutate: 51 mutant(s), 51 killed by at least one law, kill rate 1.00
$ echo $?
0

$ python -m bendeda law lint tasks/seq/B1_fifo --mutation .bend-cache/b1/mutation_la3.json
tasks\seq\B1_fifo: 22 law(s), 0 finding(s)
law lint: 1 package(s), 22 law(s), 0 finding(s)
```

Every mutant is killed and every law is killed by at least one mutant, so neither
direction of L006 is silent. Finding 2 records the run that failed, and the three
laws that closed it.

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

**2. LA3 failed at 0.804, the ten survivors were one law gap, and three laws closed it.**
The survivors were all constructor choices in `step`, and none of them was an
equivalent mutant: at line 107, `Idle` on a full FIFO returned `Empty{}` instead of
`Full{}`; at line 85, `PushPop` on an empty FIFO stopped returning `Half{}`. The
composed book accepted both, which I checked by running the mutated model against all
19 laws directly rather than trusting the scorer:

```console
$ bun main.ts .bend-cache/b1/m046_book.bend    # Idle on Full -> Empty, 19 laws
ALL PROOFS CHECK
```

Why: `f12_idle_preserves_head` asserted the head survived, and it did — the mutant
only changed the level. `f13_pushpop_empty_head` asserted the head was `din`, and it
was. `count` laws were stated over *states* (`s02`, `s03`), not over a transition's
result. So the laws constrained the data and never the occupancy a cycle produced.

Three laws close that, and the re-run is the measurement above:

| Law | Requirement | Kills |
|---|---|---|
| `fifo_f14_idle_preserves_count` | R13 (added: idle leaves occupancy alone) | `Idle` on empty, half and full (lines 87, 97, 107) |
| `fifo_f15_pushpop_empty_count` | R11 | `PushPop` on empty (line 85) |
| `fifo_f16_pushpop_full_count` | R10 | `PushPop` on full (line 105) |

R13 had to go into the specification too: behaviour item 5 stated idle without an id,
and citing R9 for a law about occupancy would have been false.

This supersedes the first report's reading of the same gate. It said
`fifo_s01_count_within_depth` was *type-enforced*; that was a statement about the
catalogue, not the law. `count` returns `Nat` and nothing stopped it returning
`3n`, but the catalogue bumped literals only on lines its arithmetic pattern
matched, and a `match` arm's body (`2n`) is not one. Adding that class makes
`m006 literal 2n -> 3n` kill `fifo_s01` at the law layer:

```console
$ bun main.ts .bend-cache/b1/attr/fifo_s01_count_within_depth.bend
SOME PROOFS FAIL
- expected : False{}
Note: the left side of the equality is the expected, the right side is the observed.
```

So the earlier 0.875 measured the catalogue's reach (48 sites, 32 tried), and 0.804
measures the laws against all 51. The second number is the honest one.

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
- LA3's 1.00 is not an independent result: the laws and proofs came from one
  session, so it shows the law set constrains the model, not that a second author
  would write the same laws.
- The package is `draft`. `locked/LOCKED.json` remains empty and
  `provenance.yaml` says `locked.by: unlocked` rather than naming a Conductor.
