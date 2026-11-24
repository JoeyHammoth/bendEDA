# SPDX-License-Identifier: Apache-2.0
# Bend 2, pinned by release version AND archive digest.
#
# The digest below was verified on 2026-11-21 by downloading the release archive
# and comparing it against both the published GitHub asset digest and the sha256
# embedded in bend-lang.com/install.sh. Both agreed:
#   c9ff8d67bd903fb6ad9a26b43d8a62c01021de82a44d55ce4a3dcd4732113d6b
#
# No clang/LLVM here: proof checking and `-o model.mjs` do not need a C toolchain.
# Add it only if a gate needs a native binary.
FROM debian:bookworm-slim

ARG BEND_VERSION=2.0.40
ARG BEND_SHA256_LINUX_X64=c9ff8d67bd903fb6ad9a26b43d8a62c01021de82a44d55ce4a3dcd4732113d6b
ARG BEND_SHA256_LINUX_ARM64=2f42a6fa34ecdaa71ae105e5fa734f9a07e129d333e45448ab6d2ff03a837570
# A local mirror for the offline build: point the base URL at a container whose
# network has no route off the machine. The digest check below is unchanged, so
# the mirror is verified rather than trusted (docs/offline-builds.md).
ARG BEND_BASE_URL=https://github.com/bendlang/bend/releases/download
# The default refuses anything but TLS. A mirror on an internal network has no
# certificate, so an offline build opts in explicitly with
# `--build-arg BEND_PROTO=https,http`; the sha256 check is what still decides.
ARG BEND_PROTO=https

ENV DEBIAN_FRONTEND=noninteractive \
    BEND_NO_TELEMETRY=1 \
    PATH=/opt/bend/bin:$PATH

# A staged archive wins over the network: `docker/archives/<name>` is populated by
# whoever prepared the offline build (never committed), and when it is present the
# image needs no curl, no CA bundle and no apt at all. The digest check is the same
# on both paths, so the staged archive is verified rather than trusted.
COPY docker/archives/ /opt/archives/

RUN set -eu; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) sum="$BEND_SHA256_LINUX_X64"; asset_arch=x64 ;; \
      arm64) sum="$BEND_SHA256_LINUX_ARM64"; asset_arch=arm64 ;; \
      *) echo "unsupported architecture: $arch" >&2; exit 1 ;; \
    esac; \
    name="bend-${BEND_VERSION}-linux-${asset_arch}.tar.gz"; \
    if [ -f "/opt/archives/${name}" ]; then \
      echo "using the staged archive ${name}"; \
      cp "/opt/archives/${name}" /tmp/bend.tgz; \
    else \
      apt-get update; \
      apt-get install -y --no-install-recommends ca-certificates curl; \
      rm -rf /var/lib/apt/lists/*; \
      curl --proto "=$BEND_PROTO" --tlsv1.2 -fsSL -o /tmp/bend.tgz \
        "${BEND_BASE_URL}/v${BEND_VERSION}/${name}"; \
    fi; \
    echo "${sum}  /tmp/bend.tgz" | sha256sum -c - ; \
    mkdir -p /opt/bend; \
    tar -xzf /tmp/bend.tgz -C /opt/bend --strip-components=1; \
    rm -f /tmp/bend.tgz; \
    rm -rf /opt/archives; \
    /opt/bend/bin/bend version

# Non-root, because the sandbox is the boundary and root is not free.
RUN useradd --create-home --uid 10002 bend
USER bend
WORKDIR /work
ENTRYPOINT ["/opt/bend/bin/bend"]
CMD ["version"]
