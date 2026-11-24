# Containers

The study needs three environments, and they are deliberately separate:

| Image | Contains | Used by |
|---|---|---|
| `harness` | Python, `bendeda`, Node (for `model.mjs`) | runner, gates, analysis |
| `bend` | pinned Bend 2 release | L0 proofs, `bend_vectors`, model execution |
| `oss-cad` | pinned OSS CAD Suite: Yosys, SBY, MCY, Verilator, Icarus, nextpnr | lint, sim, formal, mutation |

Phase 0 requires that each image builds **offline from a lockfile** and records
`bend version`, the OSS CAD Suite release and the image digest in every run.
All three images now build in CI. Two of the three parts are met and the third is
not:

- **Recorded in every gate report.** `bendeda canary --out` and
  `bendeda law mutate --out` carry an `environment` block (issue #6, criterion 2):
  the checker, and — when the checker runs in a container — the digest the daemon
  resolved (`docker image inspect`, so a rebuilt tag cannot pass for the pinned
  image) and the version the image prints for itself (`docker run <image> version`).
  A local source run says `image: none (local source pin)` rather than borrowing a
  digest it never used. The module is `bendeda/provenance.py`; the record is
  asserted in `tests/test_provenance.py`.
- **The harness image now builds offline.** `docker build --network=none -f
  docker/Dockerfile.harness` succeeds: Node is copied from
  `node:20-bookworm-slim` instead of installed with `apt-get`, and the package is
  put on `PYTHONPATH` because installing it would need a build backend fetched
  from the network. Two people are traded for that: the image no longer proves
  `pip install` works (the `tests` job does that instead), and Node is the upstream
  build rather than the distribution's.
- **The other two images still fetch one archive each.** `BEND_BASE_URL` and
  `OSS_CAD_BASE_URL` point them at a local mirror on an internal Docker network,
  and the digest check is unchanged. `docs/offline-builds.md` records what was
  measured and what is still a recipe.

## Pinned versions (2026-11-21)

| Image | Pin | Digest verified | Built |
|---|---|---|---|
| `bend` | release 2.0.40, tag commit `624dd9f` | **yes** — linux-x64 archive `c9ff8d67…` matches both the GitHub asset digest and the installer's embedded hash | **yes**, by the `bend-image` CI job |
| `osscad` | release 2026-11-20 | **yes** - the release publishes a sha256 per asset and `6e200a57...` matches it; re-checked at build | **yes**, by the `oss-cad-image` workflow |
| `harness` | python 3.12 + node 20 | n/a | **yes**, offline (`--network=none`) and in CI |

A local build on 2026-11-24 resolved to `sha256:eaf0a9d7…` and reported
`bend 2.0.40`; a canary report from that image records both in its `environment`
block, and the digest matches `docker image inspect` byte for byte.

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
# build
docker build -f docker/Dockerfile.bend      -t bendeda/bend:2.0.40 .
docker build -f docker/Dockerfile.oss-cad   -t bendeda/oss-cad:2026-11-20 .
docker build -f docker/Dockerfile.harness   -t bendeda/harness:0.0.1 .
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
