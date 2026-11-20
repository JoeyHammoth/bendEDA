# Amendments

Every change to a locked artifact, a threshold, a metric definition or the protocol
text itself lands here as a dated entry. The rule is simple: **an amendment may
change the study, but it may not hide the cost of the change.**

## When an amendment is required

| Change | Amendment? |
|---|---|
| Editing a `locked` law set, model, abstraction map or oracle component | Yes |
| Changing D1-D5 thresholds, a primary metric definition, or a frozen analysis script | Yes |
| Adding an arm, ablation or task after the freeze | Yes |
| Fixing a typo in prose that no result depends on | No |
| Fixing a harness bug that changes no recorded outcome | No, but note it in the wiki decision log |
| Adding docs, site pages, tests or CI that do not alter the protocol | No |

## How

1. Copy `TEMPLATE.md` to `YYYY-MM-DD-short-slug.md`.
2. Fill in what changed, why, which runs are invalidated, which gates were
   re-run, and the new hashes.
3. Open a pull request labelled `amendment`. The locked-file guard passes only
   with that label, and `CODEOWNERS` requires the owning role group plus the human
   release approver for one-way doors.
4. Update `locked/LOCKED.json` with the new hashes in the same pull request.
5. Bump the design-document version and add the entry to
   `bend2-agentic-eda-research-design.md` (Appendix J.10 ledger format).
6. Add a line to the wiki's `Decision-Log` page.

## What happens to collected runs

- An amendment is **behaviour-preserving** only if it can be shown to be so; that
  claim must be argued in the entry and checked by a second role group.
- Otherwise every run using the amended artifact is either re-run or excluded,
  and the exclusion is listed in the results bundle so a reader can see exactly
  which numbers changed.

The commitment to the sealed oracle is amended the same way: a new commitment is
published, and the old one stays in history so the change is auditable (design
document Appendix I.4, step 8).
