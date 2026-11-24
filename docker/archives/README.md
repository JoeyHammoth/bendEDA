# Staged build archives

Empty by default, and it stays empty in git: `*.tar.gz` and `*.tgz` here are ignored.

`docker/Dockerfile.bend` and `docker/Dockerfile.oss-cad` copy this directory and use a
staged archive in preference to the network. When the archive for the build
architecture is present, the image needs no `curl`, no CA bundle and no `apt-get` — it
builds with `docker build --network=none`. The pinned sha256 is checked on both paths,
so a staged file is verified rather than trusted.

To prepare one (the digest is checked before the build and again inside it):

```bash
name=bend-2.0.40-linux-x64.tar.gz
curl -fsSL -o "docker/archives/$name" \
  "https://github.com/bendlang/bend/releases/download/v2.0.40/$name"
echo "c9ff8d67bd903fb6ad9a26b43d8a62c01021de82a44d55ce4a3dcd4732113d6b  docker/archives/$name" \
  | sha256sum -c -
docker build --network=none -f docker/Dockerfile.bend -t bendeda/bend:2.0.40 .
```

The OSS CAD Suite needs Debian's archive for `g++`, `make`, `zlib` and `readline`, so
its offline build has a prerequisite image and a 754 MB archive:

```bash
name=oss-cad-suite-linux-x64-20261120.tgz
curl -fsSL -o "docker/archives/$name" \
  "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2026-11-20/$name"
echo "6e200a57cb7cc47a8a1a4772e3feda3777917edcb3fa5e8ee5743d962d265a7e  docker/archives/$name" \
  | sha256sum -c -
docker build -f docker/Dockerfile.oss-cad-base -t bendeda/oss-cad-base:2026-11-20 .
docker build --network=none -f docker/Dockerfile.oss-cad -t bendeda/oss-cad:2026-11-20 .
```

`docs/offline-builds.md` explains why this replaced the internal-network mirror: the
Dockerfile can fetch from a mirror, but BuildKit cannot be attached to a custom
network, so a `--network=<mirror-net>` build is not possible.
