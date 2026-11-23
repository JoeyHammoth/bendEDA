# BendEDA

**An open, pre-registered study of whether Bend 2's laws-and-proofs workflow makes agent-written hardware designs more trustworthy — and whether it adds anything over a locked specification in standard formal tooling.**

[![Licence: Apache-2.0](https://img.shields.io/badge/code-Apache--2.0-blue.svg)](LICENSE)
[![Docs: CC BY 4.0](https://img.shields.io/badge/docs-CC%20BY%204.0-lightgrey.svg)](LICENSES/CC-BY-4.0.txt)
[![Status: Phase 0](https://img.shields.io/badge/status-phase%200%20(bootstrap)-yellow.svg)](https://github.com/JoeyHammoth/bendEDA/wiki/Phase-0-Plan)
[![Docs site](https://img.shields.io/badge/docs-GitHub%20Pages-informational.svg)](https://joeyhammoth.github.io/bendEDA/)

Agentic EDA has an open-loop problem: agents emit plausible RTL with no hard ground truth, and a proof of a weak specification is worse than no proof at all, because it *looks* like assurance. This programme measures the difference between what an agent's gates tell it and what an independent hidden oracle says is true.

---

## The question

Treat the agent's own "done" claim as a classifier, and measure how well the gates it can see predict the truth.

| Arm | Visible gates | Isolates |
|---|---|---|
| **C0** | Agent-written simulation testbench | Baseline |
| **C1** | + agent-written SVA checked by SymbiYosys | Value of formal tooling |
| **C2** | + human-free *locked* SVA property pack (read-only) | Value of locking the spec |
| **C3** | + locked `LAWS.bend`, Bend reference model, conformance ladder | Value of the Bend 2 workflow |
| **C4** | C2 + C3 | Complementarity |

Primary endpoints are **FAR** (false assurance rate) and **HFP** (hidden functional pass); everything else — ER, CPVS, TF, MKR, RBV — is secondary and pre-specified in §10-11 of the design document. A null result is a result: "locking helps, Bend adds nothing over SVA" is a publishable finding.

## The conformance ladder

Bend has no hardware semantics, so a proof about a model says nothing about Verilog until the two are linked. The ladder makes that link explicit and *measures* its weakest rung instead of assuming it away.

```text
LAWS.bend ──agent proof, bend checker──▶ model.bend
model.bend ──L1 trace / L2 exhaustive / TF──▶ ref_model.sv, SVA templates
ref_model.sv + SVA ──SymbiYosys proof──▶ RTL
```

| Level | Check | Status |
|---|---|---|
| L0 | Laws proved on the model (`bend PROOF.bend`) | planned |
| L1 | Cycle-accurate trace conformance | **working** - `bendeda conformance trace`, offset self-test |
| L2 | Exhaustive conformance at reduced parameters | planned |
| L3 | Property transfer proved on RTL (BMC, k-induction, PDR) | planned |
| L4 | Bend-to-SystemVerilog emitter | out of scope (research) |

## Repository map

```text
bend2-agentic-eda-research-design.md   the design and implementation spec (v0.4)
bendeda/                               the harness package: CLI, gates, metrics, translators
  cli.py                               `bendeda` entry point
  metrics/                             §10 metric definitions, with known-answer tests
  plugins/                             plugin interfaces (§14.2)
  laws/                                law lint (L001-L015) and model mutation (LA3)
bendeda/schemas/                       JSON schemas for runs, events, tasks, policies
tasks/                                 task packages: spec, model, laws, oracle, variants
bv/                                    BendBV: bit-vector and FSM helpers with proofs
site/                                  GitHub Pages developer site for the CLI
docs/                                  protocol sources, research notes, proof cookbook
experiments/                           run matrices (trackA.yaml, ...)
results/                               aggregate tables; run bundles live as release assets
```

## Quickstart

The harness targets Python 3.12+ (3.14 is what CI runs).

```bash
git clone https://github.com/JoeyHammoth/bendEDA && cd bendEDA
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

bendeda --help
bendeda init --dry-run
python -m unittest discover -s tests -v
```

Nothing here needs a GPU, a network connection, or a Bend install to run the tests. Anything that needs the pinned Bend or OSS CAD Suite image runs in a container and is skipped with a recorded reason when the image is absent — never silently reported as passing.

## CLI

| Command | Does |
|---|---|
| `bendeda init` | Scaffold an experiment or task repository |
| `bendeda task new <name> --tier B` | Create a task package skeleton |
| `bendeda law lint <task-dir>` | Apply law rules L001-L015; exit 3 if no package was linted |
| `bendeda law mutate <task-dir>` | Mutate the model; 20 mutants and 0.9 kill rate by default (LA3) |
| `bendeda law translate ... --to sva` | Translate laws to SVA, emit a TF plan |
| `bendeda law provenance <task>` | Verify the authoring chain (Appendix J.4) |
| `bendeda tf run <task>` | Compute translation fidelity |
| `bendeda canary` | Checker negative-control suite: 32 controls, one false accept blocks the Bend arms |
| `bendeda gate run <name> --artifacts <dir>` | Run one gate standalone |
| `bendeda gate calibrate --corpus bugs/` | Gate sensitivity and specificity |
| `bendeda run <experiment.yaml>` | Execute a run matrix |
| `bendeda replay <run_id>` | Replay a run from its event log |
| `bendeda oracle score <run_dir>` | Hidden scoring (scoring host only) |
| `bendeda report <experiment>` | Tables, plots, results bundle |
| `bendeda bundle verify <dir>` | Re-check a proof-carrying design bundle |

Commands are wired but several are deliberately unimplemented stubs: they print what they will do and exit non-zero, so nothing silently pretends to work. See the [documentation site](https://joeyhammoth.github.io/bendEDA/) for usage and the [wiki](https://github.com/JoeyHammoth/bendEDA/wiki) for the running log.

## Authorship model

There is **no human author for the Bend 2 laws** in this project. Every artifact in the specification path — model, laws, abstraction map, reference proofs, parity pack and oracle — is written by a separately scoped agent under Freebuff control, with separation of duties enforced by read-only mounts, hash locks and per-artifact provenance rather than by human review. Humans act only as release approvers and incident adjudicators. The full policy is [Appendix J](bend2-agentic-eda-research-design.md#appendix-j-agent-authored-laws-the-no-human-author-amendment-v04-normative) of the design document; the one thing it must not become is one model grading its own homework, which is why J.5 exists.

## Status

| Phase | Weeks | State |
|---|---|---|
| 0 — environment, feasibility, checker validation | 1-2 | **in progress** |
| 1 — tasks, laws, oracles | 2-5 | not started |
| 2 — harness and tool layer | 3-6 | not started |
| 3 — pilot and protocol freeze | 6-7 | not started |
| 4-7 — main run, tracks B-D, analysis, release | 8-14 | not started |

The protocol is frozen only at the signed `prereg-v1` tag. Before then, everything is a draft and changes are reviewable as diffs.

## Contributing, security, citation

- [CONTRIBUTING.md](CONTRIBUTING.md) — contribution types, DCO sign-off, the law-authoring gates a task must pass.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — Contributor Covenant 2.1.
- [SECURITY.md](SECURITY.md) — private reporting for sandbox escapes and harness defects.
- [GOVERNANCE.md](GOVERNANCE.md) — who decides what, including the agent-role groups in `CODEOWNERS`.
- [CITATION.cff](CITATION.cff) — cite the protocol, not the repository.

Licences: code Apache-2.0, documents and task data CC BY 4.0. Third-party tools are never vendored; see [THIRD_PARTY.md](THIRD_PARTY.md).
