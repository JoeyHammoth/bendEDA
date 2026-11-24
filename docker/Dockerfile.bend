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

ENV DEBIAN_FRONTEND=noninteractive \
    BEND_NO_TELEMETRY=1 \
    PATH=/opt/bend/bin:$PATH

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

RUN set -eu; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) sum="$BEND_SHA256_LINUX_X64" ;; \
      arm64) sum="$BEND_SHA256_LINUX_ARM64" ;; \
      *) echo "unsupported architecture: $arch" >&2; exit 1 ;; \
    esac; \
    name="bend-${BEND_VERSION}-linux-$( [ "$arch" = amd64 ] && echo x64 || echo arm64 ).tar.gz"; \
    curl --proto '=https' --tlsv1.2 -fsSL -o /tmp/bend.tgz \
      "${BEND_BASE_URL}/v${BEND_VERSION}/${name}"; \
    echo "${sum}  /tmp/bend.tgz" | sha256sum -c - ; \
    mkdir -p /opt/bend; \
    tar -xzf /tmp/bend.tgz -C /opt/bend --strip-components=1; \
    rm /tmp/bend.tgz; \
    /opt/bend/bin/bend version

# Non-root, because the sandbox is the boundary and root is not free.
RUN useradd --create-home --uid 10002 bend
USER bend
WORKDIR /work
ENTRYPOINT ["/opt/bend/bin/bend"]
CMD ["version"]
