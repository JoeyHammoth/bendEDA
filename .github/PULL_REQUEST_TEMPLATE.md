## Summary

<!-- The smallest view that makes the point: a diff sketch, a call tree, a file tree, a table, a mermaid diagram. -->

## What claim does this let the repository make?

<!-- One sentence. If the answer is "none", say so and say why the change is still needed. -->

## Evidence

<!--
A command, a log, a test name, a benchmark number. Before/after where it applies.
"Do not claim behaviour was tested when it was only compiled."
-->

- **Before:**
- **After:**

## Checklist

- [ ] Commits are signed off (`git commit -s`) — DCO
- [ ] `python -m unittest discover -s tests` passes locally
- [ ] No protected/locked file changed without an `amendment` label and an `amendments/` entry
- [ ] New files carry an SPDX licence header
- [ ] No secrets, oracle plaintext, model weights or large binaries
- [ ] Docs/site updated if a command, metric or threshold changed

## Merge Danger

**Door:** two-way or one-way

<!--
One-way doors in this repo: publishing an oracle commitment, revealing the oracle,
creating prereg-v1, publishing a results bundle. Everything else is reversible.
-->

**Blast Radius:** one word (harness / protocol / tasks / oracle / docs / ci)
