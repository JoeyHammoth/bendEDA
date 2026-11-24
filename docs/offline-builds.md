# Offline image builds (issue #6, criterion 1)

**Decision.** "Builds offline" means `docker build --network=none` succeeds: no
container in the build has a route off the machine. Base images are pulled once,
before the build, and pinned by digest in `docker/versions.lock`. An archive a
Dockerfile downloads is fetched from a mirror named by a build argument, so the
build never needs public DNS or TLS to github.com.

That definition is the strictest one available with the tooling, and it is the only
one that can be checked by a person: either the build complains about network access
or it does not.

## What meets it today

| Image | Offline | Why |
|---|---|---|
| `harness` | **yes** | no `apt-get`, no `pip install`, Node copied from its pinned image |
| `bend` | no, by one archive | the release tarball still comes from github.com by default |
| `oss-cad` | no, by one archive | the 754 MB suite tarball comes from github.com by default |

### The harness image

```console
$ docker pull python:3.12-slim-bookworm
$ docker pull node:20-bookworm-slim
$ docker build --network=none -f docker/Dockerfile.harness -t bendeda/harness:0.0.1 .
#14 DONE 27.7s
$ docker run --rm bendeda/harness:0.0.1 --version
bendeda 0.0.1
$ docker run --rm bendeda/harness:0.0.1 validate --all
validate: 5 schema(s) valid, 0 task package(s) checked
$ docker run --rm --entrypoint node bendeda/harness:0.0.1 --version
v20.20.2
```

Two changes were needed, and both trade something away:

1. **No `apt-get`.** Node used to come from bookworm's `nodejs` package. It is now
   copied from `node:20-bookworm-slim`, which is a base image the build can have
   locally. The cost is that the image carries Node 20 from upstream rather than the
   distribution's build, and nothing else that apt used to provide (`git` was
   installed and unused).
2. **No `pip install`.** Installing the package needs a PEP 517 build backend
   (`setuptools>=69`), and `python:3.12-slim-bookworm` does not carry one, so pip
   would have to fetch it — the network access this build refuses. The image sets
   `PYTHONPATH=/work` instead, and the `tests` CI job runs
   `pip install --no-deps -e .` on a runner with a network, so the build backend is
   still exercised somewhere. The cost is that the image no longer proves the
   package installs; a job that never ran `pip install` would not notice.

CI enforces both: the `harness-image` job pulls the two base images and then builds
with `--network=none`.

## The archive path for `bend` and `oss-cad`

Both Dockerfiles fetch one release tarball. The decision is a **local mirror on an
internal Docker network**, not a vendored artifact:

```bash
# once, with a network: fetch the archives and verify them against the lock
curl -fSLO https://github.com/bendlang/bend/releases/download/v2.0.40/bend-2.0.40-linux-x64.tar.gz
sha256sum -c docker/bend-sources.sha256 --ignore-missing

# the mirror: a container with the archives, on a network with no gateway
docker network create --internal bendeda-offline
docker run -d --name bendeda-mirror --network bendeda-offline \
  -v "$PWD/mirror:/srv:ro" python:3.12-slim-bookworm \
  python -m http.server 8000 --directory /srv

docker build --network=bendeda-offline \
  --build-arg BEND_BASE_URL=http://bendeda-mirror:8000 \
  -f docker/Dockerfile.bend -t bendeda/bend:2.0.40 .
```

`--network=bendeda-offline` attaches the build to a network whose only member is the
mirror, so the only reachable URL is the mirror; the digest check in the Dockerfile
is unchanged, which is what makes the mirror untrusted-but-verified rather than
trusted. `BEND_BASE_URL` and `OSS_CAD_BASE_URL` exist for this and default to
github.com, so a developer with a network sees no difference.

**Not yet verified end to end.** The harness image above was built with
`--network=none` and the output is quoted from that run. The mirror recipe for the
two archive images is implemented as a build argument and written down here, but no
build has been run against an internal network yet, so it is a plan with a working
default path, not a measured result. Recording that difference is the point of this
file.
