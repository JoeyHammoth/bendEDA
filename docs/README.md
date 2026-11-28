# Documentation index

Four kinds of page, one job each. Nothing here is normative: the protocol is
[`bend2-agentic-eda-research-design.md`](../bend2-agentic-eda-research-design.md), and
the appendices there win over any page in this directory.

| Page | Job | Read it when |
|---|---|---|
| [`wiki/Running-the-CLI.md`](wiki/Running-the-CLI.md) | tutorial and reference | you have cloned the repository and want the CLI working |
| [`policy-proxy.md`](policy-proxy.md) | explanation | you want to know how an agent's egress is denied by default |
| [`self-hosted-runner.md`](self-hosted-runner.md) | how-to | you are provisioning the tools runner that unskips the EDA gates |
| [`offline-builds.md`](offline-builds.md) | how-to | you need to build an image with no network access |
| [`proof_cookbook.md`](proof_cookbook.md) | reference | you are writing a proof and need the idioms that close under the pin |
| [`cookbook/`](cookbook/) | examples | you want nine runnable proofs rather than prose about them |
| [`research/`](research/) | explanation | you want the measurement behind a decision |
| [`wiki/`](wiki/) | project log | you want the decision log, the phase plan or the agent roles |

## Research notes

Each note records what was measured, what it cost, and what it does not settle. They
are dated because a note is a report on a moment, not a description of the present.

| Note | What it establishes |
|---|---|
| [`2026-11-21-phase0-source-verification.md`](research/2026-11-21-phase0-source-verification.md) | the Bend 2 facts that changed the plan, checked against primary sources |
| [`2026-11-23-checker-canary.md`](research/2026-11-23-checker-canary.md) | the checker's negative controls at the pin, and which verdict modes exist |
| [`2026-11-24-b1-fifo-package.md`](research/2026-11-24-b1-fifo-package.md) | the first task package, and why it is a draft |
| [`2026-11-24-law-lint.md`](research/2026-11-24-law-lint.md) | rules L001-L015, and the mutation report L006 needs |
| [`2026-11-24-proof-cookbook.md`](research/2026-11-24-proof-cookbook.md) | 23 proof examples across S1-S9, and the one that must be refused |
| [`2026-11-24-sealed-oracle.md`](research/2026-11-24-sealed-oracle.md) | deterministic archive, Merkle commitment, verification without a key |
| [`2026-11-28-tf-run-design.md`](research/2026-11-28-tf-run-design.md) | what `tf run` has to compute, before any of it is implemented |

## Where a change goes

| You changed | Update |
|---|---|
| a command, flag or exit code | `CLI` table in [`../README.md`](../README.md), `wiki/Running-the-CLI.md`, and `site/index.html` if it is on the front page |
| a metric or a threshold | the definition in `bendeda/metrics/core.py` first, then the design document's §10 table |
| a decision, or a decision reversed | `wiki/Decision-Log.md`, newest first, with what it cost |
| a gate's behaviour | the corpus README under `experiments/corpus/`, with the command that produced the numbers |
