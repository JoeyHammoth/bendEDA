# Support

## Before you open an issue

- [`docs/wiki/Running-the-CLI.md`](docs/wiki/Running-the-CLI.md) — install, the
  exit-code contract, and the commands that work today.
- [`docs/wiki/FAQ.md`](docs/wiki/FAQ.md) — what the study is, what it is not, and
  what "phase 0" means.
- [`docs/README.md`](docs/README.md) — the documentation index, by what the page is
  for rather than by filename.
- `bendeda <command> --help` is generated from the parser, so it is the reference
  that cannot go stale.

## Where to ask

| You want | Go to |
|---|---|
| Report a defect, a wrong metric or a proof that is false | [bug form](https://github.com/JoeyHammoth/bendEDA/issues/new?template=bug.yml) |
| Propose a change to the harness, the protocol or the docs | [feature form](https://github.com/JoeyHammoth/bendEDA/issues/new?template=feature_request.yml) |
| Ask a usage question | [open an issue](https://github.com/JoeyHammoth/bendEDA/issues/new) and say it is a question |
| Start contributing | [`good first issue`](https://github.com/JoeyHammoth/bendEDA/labels/good%20first%20issue) and [`help wanted`](https://github.com/JoeyHammoth/bendEDA/labels/help%20wanted) |
| Report a vulnerability | [SECURITY.md](SECURITY.md) — the private advisory flow, never a public issue |

GitHub Discussions are not enabled. Questions and their answers belong in issues,
where they stay searchable and can turn into a documentation fix.

## What to include

- The exact command, and whether `bendeda` came from `pip install -e .` or another
  install.
- `python -m bendeda --version`, your Python version and your platform.
- Whether Docker, the pinned Bend sources (`.bend-cache/bend-2.0.40`) or the OSS CAD
  Suite image were present. A gate that reported `skipped` is not a gate that passed,
  and knowing which one you hit changes the answer.
- For a wrong result: the commit hash, the artifact directory, and the output you got
  against the output the definition says you should get.

## What this project cannot help with

- **Sealed-oracle contents**, or results from runs that have not been published. The
  oracle is sealed on a separate host by design; a support request cannot open it.
- **General Verilog, SystemVerilog or Bend tutoring.** The proof cookbook and the
  design document's appendices are the material; they are not a course.
- **Running the study's expensive gates for you.** They need a self-hosted runner and
  a pinned image, and they report `skipped` where those are absent rather than passing.
- **Changes to a law set, model, abstraction map, threshold or oracle** — those are
  protocol changes with their own process in [GOVERNANCE.md](GOVERNANCE.md), not
  support requests.

## Response expectations

This is a research repository with one maintainer. Every issue is read. No response
time is promised: a published promise that is missed is exactly the kind of claim this
project exists to stop making.
