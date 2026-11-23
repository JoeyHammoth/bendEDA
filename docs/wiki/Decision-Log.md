# Decision log

Newest first. Every entry says what was decided, what it costs, and where the authoritative text lives. Decisions that were later reversed stay in the log with a superseded marker — the log is history, not a description of the present.

---

## 2026-11-24 - Law lint reports what it could not evaluate

**Decided:** L004, L006 and L014 append a note when the package lacks the metadata they need, and `law lint` exits 3 when it found no task package at all.

**Why:** a clean report from zero packages, or from a run where half the rules were skipped, is the same false assurance as a stub exiting 0. The distinction that matters is "every applicable rule ran and found nothing", and it has to be visible in the output rather than inferred.

**Cost:** draft packages print notes that are not defects, so the report is noisier than a list of findings.

**Evidence:** `bendeda law lint tests/fixtures/law_packages/defective` reports all 15 rules and exits 1; a generated clean package produces no findings; an empty directory exits 3.

---

## 2026-11-24 - Mutation isolates each law, because the checker names one failure

**Decided:** `law mutate` inlines the mutated model ahead of each law (and the proofs it calls), and runs the checker once per law per mutant. The gate defaults are LA3's: at least 20 mutants, kill rate 0.9, no law surviving every mutant.

**Why:** Bend 2.0.40 stops at the first failing law, so one run per mutant cannot attribute kills, and `import model` is rejected at this pin. Inlining is the only portable way to check a mutated model against a single law, and a mutation gate that cannot say *which* law noticed is not evidence for LA3.

**Cost:** mutants x laws compiler runs; `--max-mutants` exists to cap a run.

**Evidence:** `docs/research/2026-11-24-law-lint.md`; `tests/test_law_mutate.py` asserts attribution with a fake checker and again through the pinned one.

---

## 2026-11-24 - BendBV states closure as mask idempotence, not a numeric bound

**Decided:** the library now proves `mask(0n, x) == 0`, `mask(32n, x) == x`, `Word.and` against the zero and all-ones words, the additive identity through `Word.adc`, `bv_add(w, mask(w, a), 0) == mask(w, a)`, and that both operations return a value the mask leaves alone. A numeric closure bound, symbolic associativity and symbolic wrap stay open in `bv/OPEN.md`.

**Why:** `Word.to_nat` ships with no laws at the pin, and `Bool.full_add` has none either, so the numeric bound and associativity cannot be stated as proved lemmas today. Stating them anyway would put an open law back in `bv.bend`, and an open law prints the same verdict as a deleted mask.

**Cost:** criterion 3 is closer but not met: the width contract is carried by in-range lemmas and a concrete 8-bit wrap, not by `to_nat(...) < 2^w`.

**Evidence:** `bend bv/bv.bend` prints `ALL PROOFS CHECK`; `bv/negative/unmasked_add.bend` is still refused; `tests/test_bv.py`.

---

## 2026-11-21 - BendBV proves the mask layer and names what it cannot prove

**Decided:** `bv/bv.bend` carries `mask`, `bv_add`, `bv_sub` and the laws that check — `Bool.and_idem/comm/assoc`, `Word.and_idem`, `Word.and_assoc`, `mask.idem`, `bv_add.comm`, and the concrete `bv_add(8n, 200, 100) == 44`. `bv/negative/unmasked_add.bend` deletes `mask(w)` and states the same wrap; it must be refused.

**Why:** exit criterion 3 asks for lemmas that check with no escape hatch, and proves only what checks. An open law prints the same `SOME PROOFS FAIL` as a deleted mask, so keeping the library clean is what lets `ALL PROOFS CHECK` mean something.

**Cost:** the width contract is carried by one concrete 8-bit claim, not by a symbolic closure lemma. Closure, identity, wrap and associativity sit in `bv/OPEN.md` beside the base lemma each one is missing; a model relying on the library beyond the proved set is relying on that file, not on the checker.

**Evidence:** `bend bv/bv.bend` prints `ALL PROOFS CHECK`; `bend bv/negative/unmasked_add.bend` prints `SOME PROOFS FAIL` with `expected 300, observed 44`; the same two assertions run in the `vector-path` and `bend-image` CI jobs; `tests/test_bv.py`.

---

## 2026-11-21 - BendBV is one file, because the two-file convention does not check reliably

**Decided:** definitions, claims and proofs share `bv/bv.bend`; the gate is `bend bv/bv.bend`.

**Why:** the guide's `LAWS.bend`/`PROOF.bend` split assumes the proof file can import the claims. On 2.0.40 an import resolves against the working directory rather than the importing file, and a path containing `.bend` is rejected ("expected: an import path of plain names"). A split would check only when the gate happened to run from a particular directory — and a CI job that ran it from the wrong one would report a pass it had not earned.

**Cost:** claims and proofs are checked together, so the claims cannot be read without the proof scripts. `bv/README.md` says which is which.

---

## 2026-11-21 - A plan drives each input, not one shared vector

**Decided:** `plan.stimulus` maps an input name to its own sequence; the manifest says `"stimulus": "plan"` (optionally with a `key`), and `--plan` supplies a file. `incs` remains the model's stimulus and keeps working.

**Why:** one shared `incs` list can only express designs whose inputs all change together. An enable that deasserts, a mode that switches, or two data inputs cannot be driven that way, and inventing a second plan format for them would have been worse than extending this one.

**Cost:** the plan is now the place where simulation-only stimulus lives, which means a task can be simulated with inputs the Bend model does not see. That is deliberate — the model is the reference for the compared output, not a description of every pin — but it must be written down, not assumed.

**Evidence:** `build_stimulus`/`validate_plan` in `bendeda/conformance/vector_path.py`; `--plan` in the CLI; tests `test_two_inputs_follow_their_own_sequences`, `test_a_missing_sequence_names_the_input`, `test_a_short_sequence_is_rejected`.

---

## 2026-11-21 - L1 generates its testbench from a port manifest

**Decided:** a simulated task supplies `dut.json` — top, clock, optional reset and enable, inputs, outputs, compared output — and the driver generates the Verilator bench. No testbench is committed or hand-edited.

**Why:** a hand-written bench per task is the same code with different port names, copied twelve times and silently diverging. Generating it makes the port list the single source of truth, and makes the generator testable: the packing, the port connections and the sample format are asserted in unit tests instead of inspected by eye.

**Cost:** the manifest cannot express multi-clock designs, handshakes or memories. That is stated in the fixture spec rather than stretched: a design outside it needs a real harness, and a generator that guessed would produce benches nobody could trust.

**Evidence:** `experiments/fixtures/toy_counter/dut.json`; `render_testbench` / `build_stimulus` / `validate_spec` in `bendeda/conformance/vector_path.py`; `TestGeneratedTestbench` in `tests/test_vector_path.py`.

---

## 2026-11-21 - L1 judges real RTL, not a second model

**Decided:** `bendeda conformance trace --dut verilator` runs the fixture's RTL under Verilator in the pinned OSS CAD image, and the gate must reject `dut_wrap.sv` as a *value* mismatch.

**Why:** comparing the Bend model against a Python function that encodes the same behaviour checks the plumbing, not the design. RTL that wraps at 16 instead of saturating is the control that proves the comparator sees a bug a version check would miss.

**Cost:** the image now carries g++ and make for `verilator --binary`, and each fixture needs its own testbench. There is no generic RTL harness until Phase 2.

**Evidence:** `experiments/fixtures/toy_counter/{dut.sv,dut_wrap.sv,tb_dut.sv}`; the CI step "The gate rejects wrapping RTL" in `.github/workflows/oss-cad-image.yml`.

---

## 2026-11-21 - The OSS CAD pin is verified by a proof, not by a version string

**Decided:** the OSS CAD image counts as pinned only when a build from the recorded digest runs a real SymbiYosys BMC that passes.

**Why:** printing `yosys -V` proves a binary exists. It does not prove the archive unpacked correctly, that the solver came with it, or that the gate that will judge RTL works. The first attempt failed twice for exactly those reasons - a missing `[files]` entry and an unreadable generated fixture - which is the kind of thing a version check would have hidden.

**Cost:** the job downloads 754 MB, so it runs only when the pin, the Dockerfile or the workflow changes, never on every pull request.

**Evidence:** `.github/workflows/oss-cad-image.yml`; digests match the release's published per-asset sha256 (`6e200a57...` x64, `d58ee2fa...` arm64); `sby` reports `DONE (PASS, rc=0)`.

---

## 2026-11-21 · The vector path runs at a pinned commit, and the gate must be able to fail

**Decided:** the L1 gate compiles the model at commit `624dd9f` (Bend 2.0.40), using either the release binary or the pinned sources under Bun 1.4.5, and every run includes an injected one-cycle offset that must be detected.

**Why:** a trace checker that reports agreement against a shifted DUT proves nothing, and the first driver agreed with everything because it accepted a wrapper *function* as a value — JavaScript serialises that to a missing JSON key, so the check passed by producing nothing. A gate without a negative control is decoration.

**Cost:** the harness depends on Bun for the source path, and the driver encodes the compiler's erased field names (`head`/`tail`, not the source's `h`/`t`). A compiler change will break the driver loudly rather than silently, which is the trade we want.

**Evidence:** PR #19; `bendeda conformance trace --inject-offset 1` reports `offset detected`; CI jobs `vector-path` and `bend-image`. Authority: Appendix K G-01, Phase 0 exit criterion 2.

---

## 2026-11-21 · No human author for Bend 2 laws

**Decided:** law, model, reference-proof, parity and oracle artifacts are authored by separately scoped agents under Freebuff control. Humans are release approvers and incident adjudicators only.

**Why:** the project has no human law author. Pretending otherwise would leave the protocol describing a workflow nobody performs.

**Cost, stated up front:** an agent law author can share an implementation agent's blind spots, which would make C3 look better than it is. Mitigations: cross-family authoring, LA3/LA4 mutation pressure, an adversarial auditor, ablation A7, and the LAW-FAR moderator analysis. Authority: design document Appendix J.

**Reversal condition:** if A7 shows FAR moving materially with author identity, that becomes a moderator in every C3/C4 claim rather than a footnote.

---

## 2026-11-23 · The canary suite scores the refusal stage, not just the verdict

**Decided:** a control counts only when it is refused at the layer it was written for; a refusal at the wrong stage fails the suite.

**Why:** Bend 2.0.40 prints `SOME PROOFS FAIL` for a false theorem, a typo, a TODO and a parse error alike. Thirty-two files that all failed to parse would report zero false accepts and prove nothing — the same hollow assurance as the unmasked-add control if it had failed on a missing import. Calibration confirmed the risk: three controls were refused for the wrong reason or accepted because they were true (`300` fits in `U32`; `U32.add_comm` exists in Base).

**Cost:** the catalog declares a stage per control, so writing a control correctly is slower than writing one that merely fails.

---

## 2026-11-23 · `verdict_available` is false at the pin, and the kernel is the reason

**Decided:** the proven-kernel checker is recorded unavailable for Bend 2.0.40 as pinned; D5 uses the canary false-accept rule plus an independent evaluator.

**Why:** the flag exists, but it needs Lean v4.34.0 and a built BendTT kernel. Exact output at the pin: `the kernel did not build (lean: Executable not found in $PATH)`. The image installs `ca-certificates` and `curl` only, so the released binary reports the same. The earlier note said a third-party 2.0.39 reproduction reported a parse error; the real blocker is the missing toolchain, which is a different fact and needs a different remedy.

**Cost:** no result may be described as kernel-validated. Enabling it would mean adding Lean and building BendTT into the pinned image, changing its digest and the trust base — a Phase 0 decision, not a quiet pin edit.

---


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
