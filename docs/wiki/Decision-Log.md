# Decision log

Newest first. Every entry says what was decided, what it costs, and where the authoritative text lives. Decisions that were later reversed stay in the log with a superseded marker — the log is history, not a description of the present.

---

## 2026-11-24 - LA3 passes only after the laws say what a cycle leaves behind

**Decided:** B1 gains three post-state laws — `fifo_f14_idle_preserves_count`,
`fifo_f15_pushpop_empty_count`, `fifo_f16_pushpop_full_count` — and the
specification gains R13 ("with neither push nor pop, occupancy is unchanged") so
the idle law has a requirement it can honestly cite. LA3 is recorded as **pass**:
51 mutants, 51 killed, kill rate 1.00.

**Why:** the previous run killed 41 of 51, and the ten survivors were not equivalent
mutants — they changed the occupancy a cycle produces (`Idle` on full emptying the
FIFO, `PushPop` on empty leaving it empty). Nothing in the law set observed that,
because every law pinned the data or the state and none pinned the transition's
result. The gate found a real hole; the response was to write the laws the hole
described, not to widen the mutant budget or delete the inconvenient law.

**Cost:** three more laws and proofs to maintain, and a new requirement id in a
specification that had not numbered the idle behaviour. The run is now 22 checker
invocations per mutant (~50 minutes locally).

**Evidence:** `tasks/seq/B1_fifo/laws.manifest.yaml` (22 entries, hashes updated);
`ALL PROOFS CHECK` on the composed book; `law lint --mutation` reports 0 findings;
the pre-change result and its diagnosis stay in
`docs/research/2026-11-24-b1-fifo-package.md`.

---

## 2026-11-24 - Deny wins in the policy proxy, and a log is re-decided before it is read

**Decided:** the proxy is deny-by-default and evaluates every deny rule before any
allow rule, so a broad allow cannot shadow a specific deny. Resources are normalised
(`..`, absolute paths and drive letters) before glob matching, and every decision —
allowed or refused — is one line in an append-only JSONL log with the rule that
fired. `bendeda replay` re-decides that log and exits 1 with the sequence number of
the first difference.

**Why:** a precedence puzzle in a security policy is a bug waiting for the third
rule. "Deny wins" removes the ordering question at the cost of making exceptions
narrow the deny rather than shadow it, which is the trade we want in a study about
false assurance. Re-deciding rather than trusting is the same principle applied to
the log: testimony until someone recomputes it from the policy.

**Cost:** the proxy is not yet the only route out — the container plumbing, budget
accounting and the `S=0` versus excluded distinction are still open, so the proxy
is the enforcement point by convention rather than by construction.

**Evidence:** `tests/test_proxy.py` (17 tests, including a real HTTP round trip on
an ephemeral port); `bendeda proxy decide --policy tests/fixtures/proxy/policy.json
--tool fs-read --resource oracle/x` exits 1 with `deny-oracle`; a Windows drive
path was accepted as relative until a test caught it.

---

## 2026-11-24 - "Offline build" means `docker build --network=none`, and only the harness image meets it

**Decided:** an image counts as offline when it builds with no route off the machine.
Base images are pulled once and pinned by digest in `docker/versions.lock`; an
archive a Dockerfile needs is fetched from a mirror named by a build argument
(`BEND_BASE_URL`, `OSS_CAD_BASE_URL`) and still verified against the pinned sha256.
The harness image drops `apt-get` and `pip install` to meet the rule; the other two
still fetch one release archive each.

**Why:** the weaker reading — "no public *package manager* access, but GitHub is
fine" — cannot be checked by anyone, and the earlier note (`--network=none` fails at
`apt-get`) was a symptom rather than the criterion. Making the harness image build
this way forces two real trades into the open: Node comes from upstream rather than
bookworm, and the image no longer proves `pip install` works, because a build backend
is itself a download. The `tests` job runs that install instead.

**Cost:** the harness image loses apt-provided tools (`git`), and CI now depends on
two base images being pullable before the offline step. The archive path for `bend`
and `oss-cad` is implemented but has not been run against an internal network, so it
is recorded as a recipe rather than as a result.

**Evidence:** `docker build --network=none -f docker/Dockerfile.harness` exits 0 and
the image reports `bendeda 0.0.1` and `node v20.20.2`; the `harness-image` CI job
pulls the two bases and then builds with `--network=none`; `docs/offline-builds.md`.

---

## 2026-11-24 - The mutation catalogue bumps bare Nat literals, because "the type enforces it" was a claim about the catalogue

**Decided:** `law mutate` now also bumps a numeric literal that is the whole body
of a line (`2n` as a match arm's body). `fifo_s01_count_within_depth` stays in B1
and is not recorded as an equivalent mutant.

**Why:** LA3's first B1 report called `s01` *type-enforced* — `count` decodes a
three-valued `Level`, so `count <= 2` could not be false. That was wrong, and wrong
in a way that mattered: `count` returns `Nat`, and nothing stops it returning `3n`.
The catalogue never edited a decode, because it bumped literals only on lines its
arithmetic pattern matched, so the gate reported the catalogue's reach as the
law's weakness. The correct reading is the one L006 is for: the law is falsifiable
and was untested.

**Cost:** three more mutants per table model (48 to 51 on B1), and each mutant is
one checker run per law. The 0.875 result this replaces came from a narrower
catalogue, which is a reason to re-run rather than to reinterpret the old number.

**Evidence:** `m006 literal 2n -> 3n` refutes `fifo_s01_count_within_depth` with
`- expected : False{}` and the checker's "left side of the equality is the
expected" note — a law-layer refusal, not a type error;
`tests/test_law_mutate.py::TestTableCatalogue`.

---

## 2026-11-24 - A gate report names the image digest it ran, not the tag it asked for

**Decided:** `bendeda canary --out` and `bendeda law mutate --out` write an
`environment` block: the checker, the digest the daemon resolved for the image, and
the version the image prints for itself. Local source runs record
`image: none (local source pin)`.

**Why:** Phase 0 criterion 2 asks every run to record `bend version` and the image
digest. A tag can be rebuilt, so `bendeda/bend:2.0.40` identifies what was
requested, not what executed. Reading the digest from the daemon is the only way to
state the latter, and a missing image has to appear as a missing digest rather than
as the repository's pin file.

**Cost:** each image-mode report costs two extra daemon calls. A run whose image
has since been pruned carries an `image_id_missing` note instead of the tag.
Offline builds remain the open half of issue #6.

**Evidence:** `bendeda/provenance.py`; `tests/test_provenance.py`; a real
`canary --local --only a01 --out` report records
`{'checker': ..., 'mode': 'default', 'image': 'none (local source pin)'}`.

---

## 2026-11-24 - The mutation catalogue mutates branches, because a table has no arithmetic

**Decided:** `law mutate` also exchanges the bodies of sibling `match` arms that bind the same names and replaces a nullary constructor with another of its declared type. A run over a law file whose laws have no proofs records `SOME PROOFS FAIL` with `1 TODO found` as an *error*, never as a kill.

**Why:** the first B1 run reported `0 mutant(s)` and exit 3 — the catalogue only edited arithmetic, and a finite transition table has none. That leaves LA3 inapplicable to exactly the model shape the specification work produces. The `TODO` reclassification fixes a false-positive that the split-law package exposed: a law with no proof prints the same `SOME PROOFS FAIL` as a refuted one, and counting that as a kill would credit the catalogue with catching a bug it never saw.

**Cost:** branch swaps double the mutant count on table models, and each mutant still costs one checker run per law (~51 s for 19 laws locally). `--max-mutants` therefore truncates by source order, so an early cap under-tests the later arms; the run's cap has to be recorded with the result.

**Evidence:** `bendeda/laws/mutate.py` (`match_arms`, `branch_swaps`, `constructor_choices`); `tests/test_law_mutate.py::TestTableCatalogue`, `test_an_incomplete_proof_is_an_error_not_a_kill`; issue #32.

---

## 2026-11-24 - B1's occupancy is an ADT, because a symbolic Nat would need an induction the property does not

**Decided:** the first task package models a depth-2 FIFO with `Level` (`Empty`/`Half`/`Full`) instead of a `Nat`, and states each law per level rather than quantifying over occupancy. Every law is then a closed computation or a three-way `match`, and all 19 close by evaluation.

**Why:** the first attempt quantified over a symbolic `Nat` for `count <= D`. `Nat.is_le` does not reduce on a symbolic argument, so the law needed an induction that the property itself does not: a proof longer than the statement is a liability under LA8, and a law that is hard to prove invites an escape hatch. The reduced instance is declared in `ambiguities.yaml` A2 and `abs.yaml` rather than hidden in the model.

**Cost:** the transition table is covered row by row, so a depth-parameterised model and a quantified occupancy bound are open work. The package README says so, and the gate table records LA3 as *not measured* rather than passing it.

**Evidence:** `tasks/seq/B1_fifo/{model.bend,LAWS.bend,PROOF_ref.bend}`; `ALL PROOFS CHECK` on the composed book; `tests/test_b1_fifo.py`.

---

## 2026-11-24 - Laws and proofs are separate files, and the composition lives in a test

**Decided:** `LAWS.bend` holds laws only, `PROOF_ref.bend` holds one same-name proof per law, and `tests/test_b1_fifo.py` composes model + laws + proofs into one book because the pin cannot import the model by path and the harness hides the reference proofs from the agent.

**Why:** the package contract in `tasks/README.md` gives the reference proofs to RPA and hides them from LAA, which a single file cannot express. Keeping the proofs in `LAWS.bend` would also hand every agent the answer key at L0, where proof engineering is the thing being measured.

**Cost:** the three files are not individually checkable, so the composition is code that must stay in step with the package layout. That is why it is a test and not a shell line in a README: a package whose proofs were never composed is a claim.

**Evidence:** `tests/test_b1_fifo.py::TestPackageChecks`; `law lint tasks/seq/B1_fifo` reports 0 findings over 19 laws.

---

## 2026-11-24 - The PEH list is code, because L007 and the harness both read it

**Decided:** the seven proof escape hatches live in `bendeda/laws/peh.py` as `EscapeHatch` records with an id, a regex, why the construct bypasses the checker, and what to do instead. L007 reports the id (`PEH-05`), and the prose table in `docs/proof_cookbook.md` is kept in step by a test.

**Why:** a list in prose cannot be consumed, and a list in the linter drifts from the guide. The old four-pattern tuple called itself a Phase 0 subset; it is gone. Two entries are not syntax the checker rejects but promises it cannot see through — a Base definition that is itself `@unsafe` (`Array.fork`, `Array.join`, `Array.get_unchecked`), and a `TODO` marker.

**Cost:** a construct the pin accepts but the list omits is invisible to L007, so adding one is a code change with a test rather than a doc edit.

**Evidence:** `tests/test_cookbook.py` asserts every entry matches its own sample, that `?TODO` is not double-counted, and that comments are skipped; `docs/research/2026-11-24-proof-cookbook.md` shows the 23 examples that check.

---

## 2026-11-24 - The commitment is over the plaintext, so verification needs no key

**Decided:** `oracle seal` hashes every component and folds the hashes into a Merkle root before encrypting; `oracle verify-commitment` recomputes them from a plaintext directory and compares. Odd Merkle levels are promoted, not duplicated, and leaves are domain-separated.

**Why:** if the commitment were over the ciphertext, only the key-holder could check it, and "verifiable pre-registration" would depend on trusting the holder. Over the plaintext, a reader who was given the oracle can check it, and a reader who was not can still check that the published root did not change. Promotion avoids the Bitcoin collision where a list and the same list with its last item doubled share a root.

**Cost:** the commitment publishes the component *names* as well as their hashes. That is intended disclosure (the task list, not the checks), and it is stated in the research note.

**Evidence:** `tests/test_oracle.py` — byte-identical archives from different mtimes and write orders, one-byte change exits 1 with both roots, `--dry-run` writes nothing.

---

## 2026-11-24 - The oracle canary GUID is public on purpose

**Decided:** `oracle_sealed/canary.txt` mints a GUID, and `tools/check_oracle_absence.py` refuses any file under `tasks/` that contains it.

**Why:** a leak is only detectable if the oracle carries a marker that must never appear in an agent's context. A secret marker cannot be checked for; a public one turns its appearance anywhere it does not belong into a finding rather than an anecdote.

**Cost:** the marker is known to every reader, so it cannot authenticate anything. It detects accidental leakage, not deliberate copying — which is the failure mode the mounts are for.

**Evidence:** the guard passes on the repository and fails on a temporary tree with the GUID in `tasks/`; `tests/test_oracle.py::TestCanaryGuard`.

---

## 2026-11-24 - The harness image is built in CI, and "offline" is not claimed

**Decided:** a `harness-image` job builds `docker/Dockerfile.harness` and runs `--version` and `validate --all` inside it. Issue #6 is reopened for the two acceptance criteria that were never met: an actual offline build, and recording the image digest plus `bend version` in each run.

**Why:** the harness image had never been built anywhere, so criterion 1's third image was an assumption. The offline criterion is different in kind: `docker build --network=none` fails at `apt-get`, not at the archive digest, so satisfying it needs a mirrored base image and a package cache — a decision about the build infrastructure, not a Dockerfile tweak. Marking the ticket done while that was unproven is the false assurance this programme studies.

**Cost:** #6 returns to the board, and criterion 1 stays partly open. The `harness-image` job adds a container build to every CI run (it is small).

**Evidence:** `.github/workflows/ci.yml` job `harness-image`; `docker/README.md`; the reopened issue's checklist.

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
