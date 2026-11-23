# bendEDA wiki

Living project notes. The **design document is the source of truth** for the protocol; this wiki is where the plan, the decisions and the running log live between releases.

> **State as of 2026-11-24.** Phase 0 (bootstrap) is done except offline image builds and digest recording ([#6](https://github.com/JoeyHammoth/bendEDA/issues/6)) and the self-hosted tools runner ([#12](https://github.com/JoeyHammoth/bendEDA/issues/12)). The first task package, `tasks/seq/B1_fifo`, exists as a **draft**: its 19 laws are proved, and its oracle, independent reference proofs, C2 parity and lock are open. Nothing is frozen: the protocol freezes only at the signed `prereg-v1` tag, so every page here describes a draft.

## Start here

| Page | What it answers |
|---|---|
| [Phase-0-Plan](Phase-0-Plan) | What has to be true before any experiment can run, and what is already true |
| [Decision-Log](Decision-Log) | Every dated decision, including the ones that were wrong |
| [Agent-Roles](Agent-Roles) | Who authors what when no human writes the laws |
| [Repository-Map](Repository-Map) | Where a thing lives, and why the layout is shaped that way |
| [Metrics-Cheat-Sheet](Metrics-Cheat-Sheet) | The endpoints in one screen, with the trap in each |
| [Running-the-CLI](Running-the-CLI) | Install, verify, and what "exit 3" means |
| [Contamination-Controls](Contamination-Controls) | How a public repository keeps a hidden oracle hidden |
| [FAQ](FAQ) | The objections we keep hearing, answered with the actual protocol |

## The one-paragraph version

Agent-written hardware designs look plausible without being correct, and formal verification only helps if the *specification* is faithful — a valid proof of a weak law is worse than no proof, because it looks like assurance. This programme compares five arms that separate formal tooling (C1), spec locking (C2) and the Bend 2 workflow (C3/C4), scores every run against a hidden oracle, and reports false assurance rather than success stories. The unusual part: **no human authors the Bend 2 laws**. Law, model, reference-proof, parity and oracle artifacts are written by separately scoped agents under Freebuff control, with independence enforced by sandboxes, hash locks and provenance records rather than by human review.

## How to use this wiki

- **Looking for a fact?** Use the design document. The wiki never claims to describe how things *are*; it records what was decided and when.
- **Looking for the current plan?** [Phase-0-Plan](Phase-0-Plan).
- **Wondering why something is weird?** [Decision-Log](Decision-Log) usually has the entry.
- **Want to help?** Issues labelled `ready-for-agent` are self-contained; the [Contributing guide](https://github.com/JoeyHammoth/bendEDA/blob/main/CONTRIBUTING.md) explains the gates.

## Links

- [Repository](https://github.com/JoeyHammoth/bendEDA)
- [Documentation site](https://joeyhammoth.github.io/bendEDA/)
- [Project board](https://github.com/users/JoeyHammoth/projects/8)
- [Design document](https://github.com/JoeyHammoth/bendEDA/blob/main/bend2-agentic-eda-research-design.md)
