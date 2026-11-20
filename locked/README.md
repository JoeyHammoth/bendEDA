# Locked artifacts

`LOCKED.json` maps repository paths to the SHA-256 they had when the Conductor
locked them. `tools/check_locked.py` refuses a pull request that changes any of
those files unless the pull request carries the `amendment` label.

The manifest does not exist yet, and that is correct: nothing is frozen. Creating
it early would lock the scaffold, which nobody needs, while missing the point that
locking is a deliberate act on a *finished* law set.

## What will be locked

At minimum, per task: `LAWS.bend`, `model.bend`, `abs.yaml`, `laws.manifest.yaml`,
`props_locked.sv`, `props_c2.sv`, `provenance.yaml`, and the oracle commitment.

## How to change a locked file

1. Copy `amendments/TEMPLATE.md` to a dated entry and argue whether the change is
   behaviour-preserving.
2. Open the pull request with the `amendment` label and update `LOCKED.json` in the
   same pull request.
3. If a run is invalidated, say which runs and add them to the results bundle's
   exclusion list. An amendment that hides its cost is worse than the defect it
   fixes.
