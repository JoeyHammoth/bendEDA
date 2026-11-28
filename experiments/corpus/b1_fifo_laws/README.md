# b1_fifo_laws corpus — the lint gate over a real law package (LA4)

A corpus for `bendeda gate calibrate` whose gate is `lint`: every entry is the shipped
B1 FIFO task package (`tasks/seq/B1_fifo`) with its law package replaced or edited. The
base supplies `model.bend`, `LAWS.bend`, `laws.manifest.yaml`, the proofs, the provenance
sidecar and the spec; an entry directory holds only the files it changes, so a defect is
a one- or two-file diff against a package that already lints clean.

| Kind | What it is | Count |
|---|---|---|
| `correct` | law packages the task accepts, structurally different from each other | 3 |
| `mutant` | one small metadata edit per entry | 3 |
| `seeded` | a plausible authoring defect, the kind a person writes | 3 |

`corpus.json` names the base, the gate set (`["lint"]`) and the entries.

```console
$ bendeda gate calibrate --corpus experiments/corpus/b1_fifo_laws
gate calibrate: b1_fifo_laws from experiments/corpus/b1_fifo_laws, gates lint
  correct/as_shipped                 accepted    lint: pass
  ...
  seeded/s02_untraceable             rejected    lint: fail — L003 laws.manifest.yaml [fifo_s01_count_within_depth]: law maps to no requirement
  per gate:
    lint       caught 6 bug(s), 6 of them alone; rejected 0 correct implementation(s)
gate calibrate: GS 1.000 (mutant 1.000 3/3, seeded 1.000 3/3), GSp 1.000 (3/3 correct)
```

Each defect is caught by the rule it was seeded for: L001 (a conditional law lost its
witness), L002 (a manifest entry with no law behind it), L003 (a law maps to no
requirement), L011 (a transferable law lost its translation), L012 (a law lost its
priority tier) and L014 (a declared hash no longer matches). The correct entries are not
three copies of one package: `retiered` changes priority metadata, and `rewritten`
rewrites a law to an equivalent form and updates both hash records — the manifest's
`hashes` and `provenance.yaml` — so L014 is shown satisfiable, not only trippable.

## What this corpus does not do

- One gate. The corpus exists because `lint` had no corpus at all; a task that carries
  both RTL and a law package would let `trace` and `lint` judge the same entries, and no
  task in this repository does yet.
- It judges the *package*, not the design: `lint` checks structure and record integrity
  (rules L001-L015), not whether a law is true. Truth is the proof ladder's job.
- The files that declare hashes must be byte-exact. Written with the platform's line
  ending, `LAWS.bend` hashes differently on Windows than on Linux and L014 fails on one
  host only — which is how the first run of this corpus scored GSp 0.333.
- The mutants are hand-written. `law mutate` mutates the model, not the manifest, so it
  cannot generate these.

## Correction (2026-11-28)

The figure above was copied forward while it was false. `props_locked.sv` was rewritten
in #59 and `variants.yaml` changed in #62, and the entries' copies of
`laws.manifest.yaml` and of `correct/rewritten/provenance.yaml` kept the old digests, so
L014 and L015 fired on packages that had no defect: the three correct entries were
rejected and GSp was 0.333 for both merges. Every copy now carries its base file's
digest and the run above was re-executed.

This is the cost of declaring a hash in a copy of a package: nothing in the harness
checks that a copy tracks its base, and a declaration that moves while a quotation of it
does not is exactly the stale-hash defect `s03` seeds — arriving through maintenance
instead of through a mistake. A corpus whose correct entries are quotations of each
other's base should re-run itself in CI; it does not yet.
