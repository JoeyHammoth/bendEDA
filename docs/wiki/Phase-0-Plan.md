# Phase 0 plan

**Goal:** nothing may depend on an unverified assumption when the first task is authored.

**Entry state (2026-11-21):** protocol v0.4 exists, the repository has governance, CI and a harness skeleton, and the metric definitions are tested. No Bend artifact exists yet, and no task package exists.

## Done

| Item | Evidence |
|---|---|
| Protocol amended for agent-authored laws | Appendix J, merged in PR #1 |
| Phase 0 gaps closed against primary sources | Appendix K, `docs/research/2026-11-21-phase0-source-verification.md` |
| Licence split, conduct, contribution, security, governance, citation | Merged in PR #2 |
| CI, hygiene tools, locked-file guard | `.github/workflows/`, `tools/` |
| CLI surface with metric definitions and known-answer tests | PR #4, 27 tests |
| GitHub Pages developer site | PR #5, `site/` |
| Issue backlog on the project board | Issues #6-#15 |
| Bend 2.0.40 pinned by archive **and** source digest | `docker/versions.lock`, `docker/bend-sources.sha256`, `bend-image` CI job (PR #19) |
| `model.mjs` vector path proven from Node, one-cycle offset detected | `bendeda conformance compile/trace`, `tools/model_vectors.mjs`, `vector-path` CI job (PR #19) |
| BendBV mask layer proved, and the unmasked control refused | `bv/bv.bend`, `bv/negative/unmasked_add.bend`, `tests/test_bv.py` |
| Checker canary suite: 32 negative and 4 positive controls, staged refusals | `bendeda canary`, `docs/research/2026-11-23-checker-canary.md`, CI `vector-path` and `bend-image` |
| `verdict_available` measured at the pin (false: no Lean toolchain) | exact command and output in `docs/research/2026-11-23-checker-canary.md` |
| `law lint` catches each seeded defect, and `law mutate` attributes a kill | `bendeda law lint`, `bendeda law mutate`, `docs/research/2026-11-24-law-lint.md`, `tests/fixtures/law_packages/` |
| BendBV proves the mask extremes, `Word.and` absorption, additive identity and in-range closure | `bv/bv.bend`, `bv/OPEN.md`, `tests/test_bv.py` |

## Open work

| # | Item | Why it blocks everything after it |
|---|---|---|
| [#6](https://github.com/JoeyHammoth/bendEDA/issues/6) | Pin the OSS CAD Suite image (Bend is done) | A result that cannot name its image digest cannot be reproduced |
| [#11](https://github.com/JoeyHammoth/bendEDA/issues/11) | Proof cookbook and PEH list | Distinguishes "law is hard" from "agent cannot prove" |
| [#12](https://github.com/JoeyHammoth/bendEDA/issues/12) | Self-hosted tools runner | Otherwise the EDA gates are skipped, and skipped is not green |
| [#13](https://github.com/JoeyHammoth/bendEDA/issues/13) | Sealed-oracle tooling | The oracle commitment is what makes pre-registration verifiable |

## Exit criteria

Phase 0 is done when all of these are true, not when the tickets are closed:

1. Three images build offline and record their digests. **Bend: built in CI from the pinned digest.** **OSS CAD Suite: built in CI from the verified digest, tools answer, and an `sby` BMC proof passes.** Harness: not yet built, and no image has been shown to build offline.
2. `bend model.bend -o model.mjs` drives a model from Node and a one-cycle injected offset is detected. **Done** — `bendeda conformance trace --inject-offset 1` reports `offset detected`.
3. BendBV's lemmas all check with no escape hatch. **Partly done** — every lemma in `bv.bend` checks (`ALL PROOFS CHECK`), including the mask extremes, `Word.and` absorption, the additive identity and in-range closure. Three claims are still open, each beside the base lemma it needs: a numeric closure bound, symbolic associativity and symbolic wrap; the FSM helpers are deferred to Phase 1. Listed in `bv/OPEN.md`.
4. **Done** — 32 negative controls and 4 positive controls; zero false accepts and zero mis-staged refusals under the default checker in both `vector-path` and `bend-image`; `verdict_available` is **false** and recorded with its exact command and output.
5. **Done** — `law lint` reports exactly L001-L015 on the seeded fixture, and zero findings on a clean package; `law mutate` returns exit 3 when no checker or no mutable site exists, so nothing is reported as measured. Evidence in `docs/research/2026-11-24-law-lint.md`.
6. The EDA gate job actually runs on the tools runner.
7. A dummy commit-reveal round-trips, and a one-byte change breaks verification.

## Deliberate non-goals

- A Bend-to-Verilog compiler (that is L4, future research).
- Track C hardware feasibility (exploratory, Phase 5).
- Any hardware-in-the-loop work (deferred extension).

## Risks being watched

| Risk | Early signal |
|---|---|
| Bend cannot be pinned to a stable release | `bend version` drift across two builds of the same image |
| `--verdict` remains broken upstream | Canary suite can only run in default mode; D5 fallback becomes permanent (G-02) |
| Proof effort swamps the token budget | BendBV proof times trending above the cap in [#8](https://github.com/JoeyHammoth/bendEDA/issues/8) |
| Self-hosted runner never provisioned | `bend-and-eda` permanently skipped → no law gates in CI |
