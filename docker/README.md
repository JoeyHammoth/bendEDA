# Containers

The study needs three environments, and they are deliberately separate:

| Image | Contains | Used by |
|---|---|---|
| `harness` | Python, `bendeda`, Node (for `model.mjs`) | runner, gates, analysis |
| `bend` | pinned Bend 2 release | L0 proofs, `bend_vectors`, model execution |
| `oss-cad` | pinned OSS CAD Suite: Yosys, SBY, MCY, Verilator, Icarus, nextpnr | lint, sim, formal, mutation |

Phase 0 requires that each image builds **offline from a lockfile** and records
`bend version`, the OSS CAD Suite release and the image digest in every run.
All three images build offline (`docker build --network=none`) and in CI, and a
matrix cell writes those facts to `environment.json` beside its score:

- **Recorded in every gate report.** `bendeda canary --out` and
  `bendeda law mutate --out` carry an `environment` block (issue #6, criterion 2):
  the checker, and — when the checker runs in a container — the digest the daemon
  resolved (`docker image inspect`, so a rebuilt tag cannot pass for the pinned
  image) and the version the image prints for itself (`docker run <image> version`).
  A local source run says `image: none (local source pin)` rather than borrowing a
  digest it never used. The module is `bendeda/provenance.py`; the record is
  asserted in `tests/test_provenance.py`. A matrix cell writes the same facts to
  `environment.json` in its bundle — `bendeda` version, `bend_release`, and the agent
  and simulator image digests — asserted in `tests/test_matrix.py`.
- **The harness image now builds offline.** `docker build --network=none -f
  docker/Dockerfile.harness` succeeds: Node is copied from
  `node:20-bookworm-slim` instead of installed with `apt-get`, and the package is
  put on `PYTHONPATH` because installing it would need a build backend fetched
  from the network. Two people are traded for that: the image no longer proves
  `pip install` works (the `tests` job does that instead), and Node is the upstream
  build rather than the distribution's.
- **The `bend` image also builds offline**, by staging the release archive in
  `docker/archives/` (gitignored) and building with `--network=none`; the pinned
  sha256 is checked on both the staged and the downloaded path. The mirror route was
  abandoned because BuildKit cannot be attached to a custom network — the error and
  the reasoning are in `docs/offline-builds.md`.
- **`oss-cad` builds offline too, from two images.** `docker/Dockerfile.oss-cad-base`
  carries the apt packages (`g++`, `make`, `zlib`, `readline`) and is built once with a
  network; `docker/Dockerfile.oss-cad` starts from it and takes the 754 MB suite from a
  staged archive, so the suite's own build runs `--network=none`. Measured 2026-11-24:
  base `#6 DONE 52.3s`, suite `#11 DONE 232.3s`, `yosys 0.71+59`, `verilator 5.055`,
  `iverilog 14.0`, and `tests.test_vector_path` runs its Verilator DUT instead of
  skipping. Publishing either image still waits on criterion 3.

## Pinned versions (2026-11-21)

| Image | Pin | Digest verified | Built |
|---|---|---|---|
| `bend` | release 2.0.40, tag commit `624dd9f` | **yes** — linux-x64 archive `c9ff8d67…` matches both the GitHub asset digest and the installer's embedded hash | **yes**, by the `bend-image` CI job; also **offline** (`--network=none`) with the archive staged in `docker/archives/` |
| `oss-cad` | release 2026-11-20, archive `6e200a57…` | **yes** — the release publishes a sha256 per asset; re-checked at build | **yes**, offline (`--network=none`) from a staged archive, in CI too; suite `sha256:41aa2359…` |
| `oss-cad-base` | debian bookworm + the apt packages | n/a | **yes**, once, with a network; `sha256:5fbcdb42…`; a prerequisite, not published (criterion 3) |
| `harness` | python 3.12 + node 20 | n/a | **yes**, offline (`--network=none`) and in CI |

A local build on 2026-11-25 resolved to `sha256:f14015d3…` (346,012,847 bytes) and a
smoke cell's `environment.json` names it; the digest matches `docker image inspect` byte
for byte. The harness image is rebuilt from the working tree, so two builds of one commit
can differ: its digest identifies the image a run used rather than pinning one. `oss-cad`
(`sha256:41aa2359…`) came back identical across rebuilds because it is built from the
staged release archive — that is the difference between a record and a pin, and the
`up` check compares package contents rather than digests for exactly this reason.

`docker/versions.lock` is the human record; `docker/bend-sources.sha256` is the
machine-checked one, consumed by `python tools/fetch_bend.py`. The Bend *source*
is pinned as well as the release, because a machine without a Linux binary (or
without Docker) can run the compiler at the same commit under Bun:

```bash
python tools/fetch_bend.py                  # fetch + verify 5 files at v2.0.40
BENDEDA_BEND_CLI=.bend-cache/bend-2.0.40/bend2/main.ts \
  python -m bendeda conformance compile --model experiments/fixtures/toy_counter/model.bend --out out/model.mjs
```

```bash
# build: CI stages the archives first and builds harness, bend and the suite with
# --network=none; see docker/archives/README.md for the two staged files
docker build -f docker/Dockerfile.harness      -t bendeda/harness:0.0.1 .
docker build -f docker/Dockerfile.bend         -t bendeda/bend:2.0.40 .
docker build -f docker/Dockerfile.oss-cad-base -t bendeda/oss-cad-base:2026-11-20 .
docker build -f docker/Dockerfile.oss-cad      -t bendeda/oss-cad:2026-11-20 .
```

## Rules

1. **Do not commit prebuilt images.** Dockerfiles and build scripts only, until a
   licence review of redistributing a GPL/LGPL toolchain is done. If images are
   later published, they must ship upstream licence texts and source references.
2. **Pin by digest**, not by tag. A run that cannot name its image digest cannot be
   reproduced.
3. **The agent container never mounts the oracle volume and has no network.**
   The policy proxy is a separate process, not a library inside the agent.
4. **No credentials in any image.** Local models need none.

## Why Bend runs in Linux

Bend's released support is macOS and Linux. Windows contributors use WSL2 or the
devcontainer; the pipeline asserts nothing about native Windows behaviour.
