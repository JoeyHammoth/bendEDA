# Task packages

One directory per task, under its tier: `tasks/<tier>/<task>/`. A package is
`draft` while it is being authored, `reviewed` after the auditor passes it, and
`locked` once the Conductor signs it. Locked means read-only: the guard in
`tools/check_locked.py` refuses a change without an `amendment` label.

```text
tasks/seq/B1_fifo/
  spec.md                 natural-language requirement, interface, parameters
  model.bend              pure reference model (step, run)          [LAA]
  LAWS.bend               laws, hash-locked                          [LAA]
  laws.manifest.yaml      law ids, classes, requirements, witnesses  [LAA]
  abs.yaml                RTL-to-model abstraction map + assumptions [LAA]
  props_locked.sv         SVA translation of the laws                [LAA]
  PROOF_ref.bend          hidden reference proofs                    [RPA]
  provenance.yaml         authoring chain (Appendix J.4)             [Conductor]
  variants.yaml           seeded variant generator declaration
  oracle/                 oracle pack: never committed in plaintext  [OAA]
  bugs/                   seeded-bug corpus and mutant tags          [OAA]
  props_c2.sv             locked SVA control pack, written from spec [PA]
```

## Rules that are not negotiable

1. **Nobody authoring `LAWS.bend` may read `oracle/`, `bugs/` or `PROOF_ref.bend`.**
   The provenance file records the attested forbidden reads, and the policy-proxy
   audit log is the evidence that the barrier held.
2. **The oracle is never committed here.** It lives in the sealed archive; this
   directory holds only the commitment reference.
3. **A task is only added to the suite after LA1-LA9 and LA9-A/B/C pass** — see
   Appendix G.6 and J.6 of the design document.
4. **`props_c2.sv` is authored from `spec.md` alone.** If it is written after the
   author sees the Bend laws, C3-versus-C2 is confounded and the task is void.
5. **Variants come from `variants.yaml`**, a pure function of `(task, seed)`, so a
   task cannot be solved by memorising a published instance.

## Why the sidecar files exist

Law metadata lives in YAML rather than inside `LAWS.bend` so that the tooling never
depends on an unverified language feature. If Bend gains a metadata mechanism, the
manifest can migrate without invalidating a single law.
