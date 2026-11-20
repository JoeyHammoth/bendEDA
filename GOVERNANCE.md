# Governance

## What this document decides

Who may change what, how a disagreement is settled, and which changes are
one-way doors. It is deliberately short: the protocol itself lives in the design
document and its appendices, and this file only says who is allowed to alter it.

## Roles

The programme has no human law author (Appendix J). Roles below are therefore
**agent role groups** scheduled by the Conductor, with one human gate at release.

| Role | Responsibility | Cannot |
|---|---|---|
| **Human release approver** (`@JoeyHammoth`) | Release sign-off, ethics, incident adjudication, external correspondence | Author law content, edit a locked law set |
| **Conductor** | Task graph, schedules, budgets, promotion to `locked`, merge decisions, tag signing | Author laws, author the oracle, or score its own runs |
| **Law-author group** (LAA + RPA) | Models, laws, manifests, abstraction maps, reference proofs | Read the oracle pack; approve their own gates |
| **Oracle-author group** (OAA + PA) | Oracle packs, golden RTL, seeded bugs, checklist, parity pack | Read law-author artifacts |
| **Auditor group** (AA) | LA-gate evidence, adversarial review, escalation | Be the same model as the LAA for the task under review |
| **Harness group** | `bendeda`, MCP servers, policy proxy, CI, metrics code | Change thresholds or metrics definitions after a freeze |
| **Community contributors** | Tasks, translators, adapters, docs, bug fixes | Merge their own changes |

Every role's write access is defined in `CODEOWNERS` and enforced by branch
protection on `main`: at least one review from the owning group, and two reviews
for anything in `tasks/`, `bv/`, `prereg/` or `amendments/`.

## Decision rules

| Decision | Rule |
|---|---|
| Merge to `main` | Green CI + owner review. The Conductor merges; it does not author. |
| Lock a law set | All of LA1-LA9 plus LA9-A/B/C pass; hashes recorded; the Conductor signs. |
| Change a **locked** law, model, abstraction map or oracle | An `amendments/` entry (reason, diff, revalidated gates, new hashes) and an `amendment`-labelled pull request. Silent edits are reverted. |
| Change a threshold, metric definition or analysis script after `prereg-v1` | Not permitted in place. A new script goes in `analysis_post/`, labelled exploratory, and the original stays executable. |
| Resolve an ambiguous spec | Deterministic adjudication rule in Appendix J.3; if behaviourally incompatible, quarantine the task. |
| Release a results claim | Conductor prepares, human approver signs, the artifact bundle hash is published. |
| Remove a maintainer or role | Human release approver, recorded in `amendments/`. |

## One-way doors

These actions cannot be undone by a revert, so they need an explicit decision
recorded in `amendments/` and the human approver's sign-off:

- publishing an oracle commitment (it fixes the oracle for the study),
- revealing the sealed oracle,
- creating the signed `prereg-v1` tag,
- publishing a results bundle or a DOI snapshot,
- deleting or rewriting published history.

## Conflict of interest

The role separation is the conflict-of-interest policy: no agent role may author
and approve the same artifact, and no role may both produce and score a run. LAI
(Appendix J.5) records model-family overlap so readers can judge independence for
themselves. Where a role is unavoidably filled by the same model, the overlap is
declared in the task's provenance file rather than concealed.

## Amendments

Protocol amendments are dated entries in `amendments/` following the template in
that directory, with: what changed, why, which locked artifacts are affected,
which runs are invalidated, and the gates re-run. Each amendment bumps the
document version and is linked from the wiki's `Decision-Log` page.

## Contact

Maintainer of record: `@JoeyHammoth` (see the GitHub profile for the contact
address). Security reports follow [SECURITY.md](SECURITY.md), not this document.
