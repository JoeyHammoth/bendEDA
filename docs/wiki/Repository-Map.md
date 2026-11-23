# Repository map

```text
bend2-agentic-eda-research-design.md   the protocol (v0.4). Normative. Appendices G-J carry the authoring, proof and public-repo standards
README.md                              the study in one page, plus quickstart
bendeda/                               the harness
  cli.py                               all 16 commands; planned ones exit 3
  metrics/core.py                      §10 definitions as pure functions
  plugins/interfaces.py                LawLanguage, Translator, Gate, Oracle, HardwareBoard
  laws/                                law lint (L001-L015), model mutation (LA3), PEH list (peh.py)
  oracle.py                            sealed-oracle archive, Merkle commitment, verification
  schemas/                             run, event, task, policy, provenance
tests/                                 stdlib unittest; metric answers, BendBV gate, law-lint fixture set
tools/                                 hygiene checkers (secrets, locked files, SPDX, whitespace, DCO, oracle absence, site)
tasks/<tier>/<task>/                   task packages; see tasks/README.md for the file contract
bv/                                    BendBV: U32 + mask(w) bit-vectors, with proofs
docker/                                pinned build definitions; Dockerfiles only, no prebuilt images
experiments/                           run matrices (pilot, trackA, ablations, B, C, D)
results/                               small aggregates only; bundles are release assets
docs/                                  research notes, wiki source, proof cookbook and its examples
site/                                  GitHub Pages developer site
amendments/                            dated amendment records and the template
oracle_sealed/                         ciphertext, commitment.json and the public canary GUID only
locked/                                LOCKED.json hash manifest (empty until the first freeze)
prereg/                                (created at Phase 3) frozen protocol, thresholds, analysis plan
```

## Why the layout is shaped this way

**The design document is at the root.** It is the artifact the study is judged on, not a secondary doc.

**`tasks/` holds law *and* oracle material side by side but with different owners.** Physical proximity is convenient; the barrier is the mount and the provenance file, not the directory. The oracle's content lives outside the repository entirely.

**`bendeda/schemas/` is inside the package** so `python -m bendeda validate` works after `pip install`, without a checkout-relative path.

**`results/` is small by policy.** A repository full of logs becomes unreviewable and unfetchable; bundles are release assets with checksums.

**`locked/` can be empty and still be meaningful.** The guard, the amendment template and the manifest format exist before the first lock, so locking is a decision rather than an improvisation.

**`docs/wiki/` mirrors the GitHub wiki.** The wiki is the living log; keeping its source reviewable in git means a decision can be reviewed like code, and a wiki outage does not lose the history.

## Where to look for what

| Question | File |
|---|---|
| Why is C2 needed if C1 exists? | design doc §5.2, §3.1 H2 |
| What exactly is "false assurance"? | §10.2, `bendeda/metrics/core.py` |
| Who wrote these laws? | `<task>/provenance.yaml`, Appendix J |
| Why does `canary` exit 3? | no checker could run; it prints why rather than passing | wiki Running-the-CLI, decision log 2026-11-23 |
| What stops me editing a locked law? | `tools/check_locked.py`, `CODEOWNERS` |
| How is the oracle hidden in a public repo? | Appendix I.4, wiki Contamination-Controls |
| How does an agent write a proof? | `docs/proof_cookbook.md`, `docs/cookbook/` |
| How is a commitment verified without the key? | `bendeda/oracle.py`, `docs/research/2026-11-24-sealed-oracle.md` |
