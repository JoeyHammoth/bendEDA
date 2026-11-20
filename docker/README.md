# Containers

The study needs three environments, and they are deliberately separate:

| Image | Contains | Used by |
|---|---|---|
| `harness` | Python, `bendeda`, Node (for `model.mjs`) | runner, gates, analysis |
| `bend` | pinned Bend 2 release | L0 proofs, `bend_vectors`, model execution |
| `oss-cad` | pinned OSS CAD Suite: Yosys, SBY, MCY, Verilator, Icarus, nextpnr | lint, sim, formal, mutation |

Phase 0 requires that each image builds **offline from a lockfile** and records
`bend version`, the OSS CAD Suite release and the image digest in every run.

```bash
# build (Phase 0.1 — not yet automated)
docker build -f docker/Dockerfile.bend      -t bendeda/bend:2.0.39 .
docker build -f docker/Dockerfile.oss-cad   -t bendeda/oss-cad:2026-11 .
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
