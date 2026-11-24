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
| `oss-cad` | no | needs `g++`, `make`, `zlib`, `readline` from apt; an archive mirror does not help |

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

## What oss-cad still needs

The suite image installs `ca-certificates curl tar xz-utils python3 libstdc++6 zlib1g
libreadline8 g++ make` with `apt-get`. Staging the 754 MB tarball removes the archive
download but not that dependency, so it needs an apt mirror or a prebuilt base image
carrying those packages. Both are infrastructure decisions with real costs (an apt
mirror is a stateful service; a prebuilt base is a published image, which criterion 3
forbids until the GPL/LGPL notice review). That is why this row is still open rather
than documented as a recipe.

## Reproducing the checks

CI enforces the two paths that exist: the `harness-image` job pulls the two base images
and builds with `--network=none`, and the `bend-image` job builds the archive path.
The commands above are the same ones, run locally.
