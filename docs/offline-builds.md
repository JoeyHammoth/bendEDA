# Offline image builds (issue #6, criterion 1)

**Decision.** "Builds offline" means `docker build --network=none` succeeds: no
container in the build has a route off the machine. Base images are pulled once,
before the build, and pinned by digest in `docker/versions.lock`. An archive a
Dockerfile needs is **staged in the build context** and verified against its pinned
sha256, rather than downloaded during the build.

That is the strictest definition the tooling allows, and the only one a person can
check: either the build complains about network access or it does not.

## What meets it today

| Image | Offline | Why |
|---|---|---|
| `harness` | **yes** | no `apt-get`, no `pip install`; Node copied from its pinned image |
| `bend` | **yes** | the release archive is staged, so the build skips `curl` and `apt` entirely |
| `oss-cad` | **yes** | Debian's packages arrive in a prerequisite base image; the suite itself comes from a staged archive |

### Harness

```console
$ docker build --network=none -f docker/Dockerfile.harness -t bendeda/harness:0.0.1 .
#14 DONE 27.7s
$ docker run --rm bendeda/harness:0.0.1 --version
bendeda 0.0.1
$ docker run --rm --entrypoint node bendeda/harness:0.0.1 --version
v20.20.2
```

Two trades: Node comes from `node:20-bookworm-slim` rather than bookworm's package,
and the package is on `PYTHONPATH` because installing it would need a PEP 517 backend
from the network (the `tests` job runs `pip install -e .` instead).

### Bend

```console
$ curl -fsSL -o docker/archives/bend-2.0.40-linux-x64.tar.gz \
    https://github.com/bendlang/bend/releases/download/v2.0.40/bend-2.0.40-linux-x64.tar.gz
$ sha256sum docker/archives/bend-2.0.40-linux-x64.tar.gz
c9ff8d67bd903fb6ad9a26b43d8a62c01021de82a44d55ce4a3dcd4732113d6b   (matches docker/versions.lock)
$ docker build --network=none -f docker/Dockerfile.bend -t bendeda/bend:2.0.40 .
#10 DONE 22.7s
$ docker run --rm bendeda/bend:2.0.40 version
bend 2.0.40
```

`docker/Dockerfile.bend` copies `docker/archives/` and prefers a staged archive:
when it is present, the build runs no `curl`, installs no CA bundle and does no
`apt-get`. The digest check runs on both paths, so a staged file is verified rather
than trusted. `docker/archives/*.tar.gz` is gitignored; the directory keeps a README.

### Why not a mirror on an internal Docker network

The earlier plan was a mirror container on `docker network create --internal` and a
build attached to it. The Dockerfile side worked — `BEND_BASE_URL`, `BEND_PROTO` and
`OSS_CAD_BASE_URL`, `OSS_CAD_PROTO` exist and default to TLS on github.com — but the
build side does not:

```console
$ docker build --network=bendeda-offline --build-arg BEND_BASE_URL=http://bendeda-mirror:8000 .
ERROR: failed to build: network mode "bendeda-offline" not supported by buildkit
       — you can define a custom network for your builder using the network
       driver-opt in buildx create
```

BuildKit accepts only `default`, `none` and `host`. The documented workaround is a
`docker-container` builder created with `--driver-opt network=<name>`, but that builder
must pull its own base images, which an internal network forbids — so it moves the
problem rather than solving it. Staging the archive in the context is strictly
stronger: the build has no HTTP client at all.

The two `*_PROTO` arguments stay, because they are what would make a mirror work if a
future builder can attach to one; with a staged archive they are unused.

### OSS CAD Suite

The suite cannot install its own prerequisites offline — `g++`, `make`, `zlib` and
`readline` come from Debian's archive, and a mirror of release tarballs cannot supply
packages — so the image is split in two:

| Image | Network | Why |
|---|---|---|
| `bendeda/oss-cad-base:2026-11-20` (`docker/Dockerfile.oss-cad-base`) | needed, built once | the apt packages; a prerequisite, not a published artifact |
| `bendeda/oss-cad:2026-11-20` (`docker/Dockerfile.oss-cad`) | **none** | the suite itself, from a staged archive |

```console
$ curl -fsSL -o docker/archives/oss-cad-suite-linux-x64-20261120.tgz \
    https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2026-11-20/oss-cad-suite-linux-x64-20261120.tgz
$ sha256sum docker/archives/oss-cad-suite-linux-x64-20261120.tgz
6e200a57cb7cc47a8a1a4772e3feda3777917edcb3fa5e8ee5743d962d265a7e   (754,324,403 bytes; matches docker/versions.lock)
$ docker build -f docker/Dockerfile.oss-cad-base -t bendeda/oss-cad-base:2026-11-20 .
#6 DONE 52.3s
$ docker build --network=none -f docker/Dockerfile.oss-cad -t bendeda/oss-cad:2026-11-20 .
#11 DONE 232.3s
$ docker run --rm bendeda/oss-cad:2026-11-20 yosys -V
Yosys 0.71+59 (git sha1 d9358f38c, Release, Clang /usr/bin/clang++ 21.1.8)
$ docker run --rm bendeda/oss-cad:2026-11-20 verilator --version
Verilator 5.055 devel rev v5.054-340-g53a72711e (mod)
```

The 232 s is mostly the 754 MB archive crossing the daemon's build context, not
compilation; the unpacked image is 5.35 GB. What matters is the second line: the build
that produced those binaries had no route off the machine.

With the image present, `tests.test_vector_path` runs its Verilator DUT instead of
skipping it — 27 tests, OK, 114.9 s — which is the check that the tools work rather than
merely answer `--version`.

A `--network=none` build cannot pull, so the base image is a prerequisite that must be
built first; `docker/versions.lock` records both digests. Publishing either image is
still gated on criterion 3's GPL/LGPL notice review — building one locally, with the
packages named in `Dockerfile.oss-cad-base`, is what this change can honestly claim.

## Reproducing the checks

CI enforces all three paths: `harness-image` pulls its two base images and builds with
`--network=none`; `bend-image` stages the release archive and builds with
`--network=none`; `oss-cad-image` stages the suite archive, builds the toolchain base,
then builds the suite with `--network=none`. The commands above are the same ones, run
locally.
