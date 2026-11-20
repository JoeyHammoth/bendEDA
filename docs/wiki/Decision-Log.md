# Decision log

Newest first. Every entry says what was decided, what it costs, and where the authoritative text lives. Decisions that were later reversed stay in the log with a superseded marker — the log is history, not a description of the present.

---

## 2026-11-21 · No human author for Bend 2 laws

**Decided:** law, model, reference-proof, parity and oracle artifacts are authored by separately scoped agents under Freebuff control. Humans are release approvers and incident adjudicators only.

**Why:** the project has no human law author. Pretending otherwise would leave the protocol describing a workflow nobody performs.

**Cost, stated up front:** an agent law author can share an implementation agent's blind spots, which would make C3 look better than it is. Mitigations: cross-family authoring, LA3/LA4 mutation pressure, an adversarial auditor, ablation A7, and the LAW-FAR moderator analysis. Authority: design document Appendix J.

**Reversal condition:** if A7 shows FAR moving materially with author identity, that becomes a moderator in every C3/C4 claim rather than a footnote.

---

## 2026-11-21 · BendBV uses `U32` + `mask(w)`, not `Nat`

**Decided:** bit-vectors are `U32` with an explicit width mask; `w > 32` is out of scope for v1.

**Why:** the released guide states that `Nat` literals above `256n` are `U32.to_nat` underneath and cap at `4294967295n`, and that `U32` is the only released type with bit operations. The v0.3 draft assumed a `Nat` encoding capped at 2^48-1; that was wrong.

**Cost:** tasks needing widths above 32 are excluded from Tier A, and the model layer has two numeric representations to keep straight.

---

## 2026-11-21 · `--verdict` is treated as unavailable until re-measured

**Decided:** Phase 0 records `verdict_available`; if false, ablation A5 leaves the confirmatory set, `CDC` is reported not measurable, and D5's `CDC = 0` clause is replaced by default-checker canary false-accepts plus an independent evaluator.

**Why:** a dated third-party reproduction on Bend 2.0.39 reports `--verdict` failing with `parse error: expected '1'`, including for `{0n == 0n : Nat}`. One reproduction is not proof, so we re-measure rather than inherit either conclusion.

**Cost:** the strongest available trust statement for proofs may be unavailable for the whole study. That limitation will appear in the trust-base statement rather than being quietly dropped.

---

## 2026-11-21 · One static site, not MkDocs

**Decided:** `site/` is hand-written HTML/CSS/JS deployed by GitHub Actions; `docs/` keeps protocol sources; the wiki holds the living log.

**Why:** the protocol already exists as Markdown in git. A generator adds a build dependency and a second rendering of the same facts, and §I.11's MkDocs plan was never verified against a real requirement.

**Cost:** no automatic docs-from-code; the CLI table on the site must be updated by hand when a command changes. `tools/check_site.py` catches broken links, not stale prose.

---

## 2026-11-21 · Stubs exit 3, never 0

**Decided:** `bendeda` commands that are not implemented print their plan and exit non-zero.

**Why:** a stub that succeeds is a small instance of the exact failure this programme studies — visible assurance that is not assurance. An agent must never be able to believe `bendeda canary` ran.

**Cost:** scripts that call planned commands fail. That is the intended behaviour.

---

## 2026-11-21 · Run bundles as release assets, no DVC dependency

**Decided:** text in git, bundles as release assets with `SHA256SUMS`, DVC only if bundles outgrow the release limit.

**Why:** one fewer tool to install on a reader's machine, and the checksum file is verifiable with `sha256sum` alone. Authority: Appendix K G-05.

---

## 2026-11-21 · Harness and hygiene scanners read `git ls-files`

**Decided:** scanners enumerate tracked files, not the filesystem.

**Why:** a working tree holds `.env`, virtualenvs and agent skills. Scanning it either fails locally for the wrong reason or misses published files. The first CI run did exactly this and produced 64 false positives.

---

## 2026-11-20 · Arms, endpoints and decision rules frozen in draft (v0.3)

**Decided:** five arms, FAR and HFP as primary endpoints, D1-D5 decision rules, simulation-based power analysis at Phase 3.

**Why:** the study is only credible if the analysis plan exists before the data. Nothing here is final until `prereg-v1`.
