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

## Open work

| # | Item | Why it blocks everything after it |
|---|---|---|
| [#6](https://github.com/JoeyHammoth/bendEDA/issues/6) | Pin the OSS CAD Suite image (Bend is done) | A result that cannot name its image digest cannot be reproduced |
| [#8](https://github.com/JoeyHammoth/bendEDA/issues/8) | Build BendBV on `U32` | Every model needs modular arithmetic that someone has proved |
| [#9](https://github.com/JoeyHammoth/bendEDA/issues/9) | Canary suite + `verdict_available` | A checker that accepts a false law invalidates every Bend arm |
| [#10](https://github.com/JoeyHammoth/bendEDA/issues/10) | `law lint` and `law mutate` | LA3-LA7 cannot be evaluated by hand at 12 tasks |
| [#11](https://github.com/JoeyHammoth/bendEDA/issues/11) | Proof cookbook and PEH list | Distinguishes "law is hard" from "agent cannot prove" |
| [#12](https://github.com/JoeyHammoth/bendEDA/issues/12) | Self-hosted tools runner | Otherwise the EDA gates are skipped, and skipped is not green |
| [#13](https://github.com/JoeyHammoth/bendEDA/issues/13) | Sealed-oracle tooling | The oracle commitment is what makes pre-registration verifiable |

## Exit criteria

Phase 0 is done when all of these are true, not when the tickets are closed:

1. Three images build offline and record their digests. **Bend: built in CI from the pinned digest.** **OSS CAD Suite: built in CI from the verified digest, tools answer, and an `sby` BMC proof passes.** Harness: not yet built, and no image has been shown to build offline.
2. `bend model.bend -o model.mjs` drives a model from Node and a one-cycle injected offset is detected. **Done** — `bendeda conformance trace --inject-offset 1` reports `offset detected`.
3. BendBV's lemmas all check with no escape hatch.
4. 30+ canary controls, zero false accepts, `verdict_available` recorded with evidence.
5. `law lint` catches each seeded defect in its fixture set.
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
