# Agent roles

There is no human law author. This page is the practical view of Appendix J; the appendix is normative.

## The roles

| Role | Writes | Must not read | Scored on |
|---|---|---|---|
| **Conductor** | task graph, manifests, locks, merges | — | protocol integrity |
| **LAA** | `model.bend`, `LAWS.bend`, witnesses, `abs.yaml`, `props_locked.sv`, manifest | oracle, seeded bugs, `PROOF_ref.bend`, agent traces | law discrimination (LA3-LA6) |
| **RPA** | `PROOF_ref.bend` + effort log | oracle, traces | provability within the effort cap |
| **OAA** | oracle TB, oracle SVA, golden RTL, seeded bugs, checklist | **every LAA artifact** | oracle recall on the bug corpus |
| **PA** | `props_c2.sv` | the Bend laws, the oracle | parity within 5 pp |
| **AA** | LA-gate evidence, adversarial review | oracle plaintext | defects found |
| **IA** | the RTL and `PROOF.bend` under test | every protected path | the arm's visible gates (and nothing else) |

## How independence is enforced, not promised

1. **Separate Freebuff runs.** Different session, different workspace, no shared conversation. Roles communicate through committed files and issue links only.
2. **Read-only mounts.** The policy proxy mounts protected paths read-only and logs every read attempt.
3. **Different model families** where the compute budget allows, recorded per artifact. A same-family LAA/OAA pair is refused by the provenance check unless declared.
4. **Different objectives.** LAA is rewarded for discrimination, OAA for recall, AA for findings. No role is scored on another role's metric.
5. **Hash locks.** Once `locked`, a law file changes only through an amendment.
6. **Evidence, not sidecars.** The policy-proxy audit log is the proof the barrier held; `provenance.yaml` is a claim about it.

## The failure this invites

A law author and an implementation agent from the same model family can agree on the same blind spot: the laws omit what that family tends to omit, the agent passes easily, and C3 looks strong while measuring little.

Four defences, all pre-registered:

- **Mutation pressure** (LA3, LA4): a blind-spot law set fails to kill plausible bugs.
- **Independent oracle recall**: OAA's kill rate is measured against the same corpus.
- **Adversarial auditor**: AA proposes implementations that satisfy every law and violate `spec.md`.
- **Ablation A7 + LAW-FAR**: same-family versus cross-family FAR becomes a moderator, not noise.

## Ambiguity, resolved deterministically

If LAA and OAA read the spec differently:

1. both readings are published in `ambiguities.yaml`;
2. the reading **stricter on the design** becomes the law; the other becomes an oracle-only requirement;
3. if the readings are behaviourally incompatible, the task is **quarantined** — never silently resolved.

## What a human still does

Release approval, ethics, external correspondence, and adjudication of an unresolved blocker. A human may spot-check 3% of locked law sets for quality. No human writes law content.
