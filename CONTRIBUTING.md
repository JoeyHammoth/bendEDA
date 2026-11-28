# Contributing to BendEDA

This is a research repository before it is a software project. A contribution is
welcome if it makes the *protocol* more trustworthy or the *harness* more
reproducible; it is rejected if it makes a result look better than it was.

Two rules sit above all others:

1. **Nothing in the specification path is authored by the implementer.** Laws,
   models, abstraction maps and oracles are produced under the role separation of
   Appendix J. A pull request that lets an implementation agent edit a law it is
   also proving will not be merged, however good the code.
2. **A claim without evidence is a defect.** Every performance, correctness or
   assurance claim in a pull request needs a command, a log or a test that
   produced it. "Should work" is not a review comment; it is a blocker.

## Ways to contribute

| Contribution | What it needs | Review |
|---|---|---|
| **New task package** | `spec.md`, model, laws, manifest, reference proofs, oracle, variants; passes LA1-LA9 and LA9-A/B/C | Two role groups (law and oracle) |
| **New or changed law set** | Fidelity report, LA3/LA4 evidence, second independent authoring run (LSS) | Law-author group + auditor |
| **New translator** | Translation + TF report (mean >= 0.999, min >= 0.99), human-readable mapping | Translator + auditor |
| **New gate / metric / oracle** | Plugin per §14.2, known-answer test fixtures, declared inputs | Harness group |
| **New agent or tool adapter** | Runs in the standard sandbox, budget accounting, policy metadata | Harness group |
| **Bug fix / docs / site** | A failing test or a sentence that is wrong | One maintainer |
| **Protocol change** | An entry in `amendments/` and a new tag; see [GOVERNANCE.md](GOVERNANCE.md) | All groups + human release approver |

## A first contribution

Issues labelled [`good first issue`](https://github.com/JoeyHammoth/bendEDA/labels/good%20first%20issue)
are scoped to be finished in an afternoon by someone who has not read the protocol:
each names the files to touch, the command that proves the change, and what is out
of scope. [`help wanted`](https://github.com/JoeyHammoth/bendEDA/labels/help%20wanted)
is the same for work that needs a particular environment or more context.

- Comment on the issue to claim it, and the maintainer assigns it to you so nobody
  solves it twice.
- A typo, a broken link or a sentence that is wrong needs no issue first — open the
  pull request.
- Anything that changes a law, model, abstraction map, threshold or oracle component
  is not a first contribution: those go through the role separation in Appendix J,
  because a reviewer has to be able to tell the author from the implementer. See
  [SUPPORT.md](SUPPORT.md) if you are unsure which surface you are on.

There is one maintainer. Every issue is read; no response time is promised, because
a promise that is not kept is worse evidence than no promise at all.

## Development setup

The README's quickstart, verbatim on a clean clone:

```bash
git clone https://github.com/JoeyHammoth/bendEDA
cd bendEDA
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

That is enough for the whole suite: nothing in it needs a network connection after
the install, a GPU, a Bend install or Docker. Gates that do need an image report
`skipped` with the reason, and a skip is never counted as a pass.

| What | Command |
|---|---|
| Every test (what CI runs) | `python -m unittest discover -s tests -v` |
| One test file or class | `python -m unittest tests.test_gates.TestLockedPackOrdering -v` |
| Schemas and task packages | `python -m bendeda validate --all` |
| Secrets, licence headers, whitespace, oracle absence | `python tools/check_secrets.py .` (and the other `tools/check_*.py`) |
| Formatting and types, if installed | `ruff check .`, `mypy bendeda` |

`make test`, `make hygiene` and `make validate` wrap the same commands where `make`
is installed. CI calls the Python commands directly, so a machine without `make` is
not a machine that cannot contribute. `.devcontainer/devcontainer.json` installs the
package and runs the suite when the workspace is created, which is what Codespaces
uses.

## Workflow

1. **Open an issue first** for anything larger than a typo, using the templates.
   State the claim you want the repository to be able to make afterwards.
2. **Branch from `main`**, name it `<type>/<short-slug>` (`feat/`, `docs/`,
   `chore/`, `fix/`).
3. **Commit in small, reviewable steps** with conventional-commit subjects. Sign
   off every commit (DCO):
   ```bash
   git commit -s -m "feat(metrics): add pass@k estimator with known-answer test"
   ```
   The sign-off certifies you have the right to submit the contribution. It is
   required; the CI job `dco` fails without it.
4. **Run the checks locally** before pushing:
   ```bash
   python -m unittest discover -s tests -v
   python -m bendeda --help
   ```
   Anything requiring the pinned Bend or OSS CAD Suite image is documented in
   `docker/`; contributors without the image are not blocked from merging
   non-hardware changes.
5. **Open a pull request** using the template. Fill in Summary, Evidence and
   Merge Danger honestly — the merge-danger section exists because some changes
   (locking a law set, publishing an oracle commitment, changing a threshold)
   are one-way doors.
6. **Squash on merge** is disabled; use merge commits so the review history
   survives. Branch deletion on merge is enabled.

## What gets a pull request closed

- Weakening, deleting or skipping a check so that a run passes.
- Changing a locked file without an `amendment` label and an `amendments/` entry.
- Adding a dependency that is not open-source and free of charge for CI.
- Committing anything from the sealed oracle, a credential, a model weight or a
  large binary artifact.
- Benchmark data redistributed in-tree (fetch it at run time instead).

## Quality gates you should expect

| Check | Blocks merge |
|---|---|
| `python -m unittest` (metrics, CLI, schemas) | yes |
| Schema validation of any changed task/policy/log file | yes |
| Locked-file guard (`locked/` hashes) | yes |
| Secret scan over the diff | yes |
| Licence headers present on new files | yes |
| Law lint L001-L015 on changed task packages | yes, where a Bend image is available |
| Canary suite (checker false accepts) | yes, where a Bend image is available |
| Docs build | yes |

Where a required component is unavailable (for example no self-hosted runner
with the Bend image), the job reports **skipped with a reason**. It never reports
a pass it did not earn.

## Style

- Python 3.12+, standard library first; a dependency needs a justification in the
  pull request.
- Type hints on public functions; no bare `except`.
- Markdown: one sentence per line is preferred, hard-wrapped prose is fine, no
  trailing whitespace.
- Metrics and thresholds live in code with tests, never in a notebook only.

## Reporting a problem in the protocol

If you believe a law set, oracle component, threshold or metric is wrong, open an
issue with the `type: bug` label and the evidence. Do not quietly change it in a
pull request: an unannounced change after a freeze invalidates the runs that
depended on it, which is exactly the failure mode this repository exists to
prevent.
