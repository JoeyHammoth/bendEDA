# B1 FIFO: the first task package, as a draft

**Question.** Can the repository carry a complete task package — spec, model,
laws, manifest, abstraction map, reference proofs, SVA, provenance — whose laws
are all closed by the pinned checker, and what does that exercise expose?

**Answer.** Yes for LA1, LA2 and LA8: 19 laws are closed by the composed book and
`law lint` reports zero findings. LA3 is *not measured*, and the reason is a tool
gap rather than a modelling choice: the mutation catalogue has nothing to mutate
in a constructor table. Everything that needs a second role (RPA proofs, PA's C2,
OAA's oracle) or an EDA toolchain is open and is named in the package README.

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
  note: L006 not evaluated: no mutation report was supplied
law lint: 1 package(s), 19 law(s), 0 finding(s)

$ python -m unittest tests.test_b1_fifo -v
Ran 9 tests in 3.590s
OK

$ python -m bendeda law mutate tasks/seq/B1_fifo --local \\\n      --out .bend-cache/b1/mutation.json
law mutate: note: the model has no site this catalogue can mutate
law mutate: 0 mutant(s), 0 killed by at least one law, kill rate 0.00,
            19 law(s) survived every mutant; below the pre-registered minimum of 20
$ echo $?
3
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

## Two findings

**1. A finite transition table is invisible to the current mutation catalogue.**
`bendeda law mutate` swaps arithmetic operators (`U32.add` to `U32.sub`, ...) and
bumps literals on lines that mention arithmetic. The B1 model has no arithmetic:
it matches on occupancy and moves constructor values. The gate therefore reports
"nothing measured" and exits 3, which is the correct behaviour for a gate that
cannot measure — but LA3 needs mutants that this catalogue cannot produce.
Candidates for a follow-up: branch swaps (`case Half{}` and `case Full{}`
exchanged), dropped guards (treat `Full` as `Half`), and constructor mutation
(`Push` accepted as `Idle`). None of these is safe to add without the well-typed
guarantee the current swaps have, which is why it is an issue and not a patch.

**2. The reduced ADT model is what makes the proofs close.**
Every law that mentions a symbolic occupancy is stated per level and proved by
`match`; every other law is a closed computation. A `Nat` occupancy would have
needed an induction over `Nat.is_le`, and the first attempt to quantify over a
symbolic `Nat` was abandoned rather than turned into a long proof. That decision
is recorded in the model header and in `ambiguities.yaml` A2, because it is a
limitation of the law set, not a property of the design.

## What the package cannot claim

- `PROOF_ref.bend` is correct but not independent: the same session wrote the
  laws and the proofs.
- `props_c2.sv` was written in the same session, after the laws. Parity between
  LC(C2) and LC(C3) from these two files would be confounded (LA6).
- Neither SVA pack has been elaborated: no SystemVerilog toolchain is installed
  locally and the OSS CAD image was not asked to run one.
- No oracle pack exists, so no sealed commitment is recorded and no seeded bug
  corpus exists for LA4/LA5.
- The package is `draft`. `locked/LOCKED.json` remains empty and
  `provenance.yaml` says `locked.by: unlocked` rather than naming a Conductor.
