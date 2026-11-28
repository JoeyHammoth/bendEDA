# Licence inventory for the three pinned images

Issue #6, criterion 3: no prebuilt image is published until a GPL/LGPL notice
review is done. This file is the inventory that review needs — which copyleft
components a published image would carry, where their licence text already is, and
which notices are missing. It does not decide the review; it makes it a sign-off
rather than research.

Measured 2026-11-28 against the images named in `docker/versions.lock`. Every fact
below was read from inside the image, and the commands are at the end.

## What this is not

- Not legal advice, and not a per-package copyright audit: for 19 (harness), 20
  (bend) and 57 (oss-cad-base) of the Debian packages, `debian/copyright` is prose
  or `License:` is not machine-readable, so those are counted, not classified.
- Not a claim that publishing is fine or not fine. It lists what would be
  distributed and what the notices cost.

## The images

| Image | Base (pinned by digest) | Debian packages | Packages whose `License:` is machine-readable | Copyleft-declared |
|---|---|---|---|---|
| `bendeda/harness:0.0.1` | `python:3.12-slim-bookworm@sha256:b123…`, `node:20-bookworm-slim@sha256:2cf0…` | 106 | 87 | 60 |
| `bendeda/bend:2.0.40` (+ `:2.0.40-offline`) | `debian:bookworm-slim@sha256:e67e…` | 107 | 87 | 55 |
| `bendeda/oss-cad:2026-11-20` | `bendeda/oss-cad-base:2026-11-20@sha256:5fbcdb42…` (160 packages) | 160 | 103 | 61 |

"Copyleft-declared" counts the `License:` fields containing GPL, LGPL or Artistic;
it undercounts, because the unreadable set includes `libc6` (prose LGPL-2.1+) and
`libstdc++6`/`libgcc-s1`/`g++` (prose, with the GCC Runtime Library Exception —
`grep -c "Runtime Library Exception" /usr/share/doc/gcc-12-base/copyright` → 4).

## Components that carry obligations

Every row was confirmed from the licence text shipped in the image, not from a
repository file recalled from memory.

| Component | Licence | Where the text is | Source reference |
|---|---|---|---|
| Bend 2.0.40 | Apache-2.0 | **not in the image** (see gaps) — the text is in the pinned source tree, `.bend-cache/bend-2.0.40/LICENSE` | `github.com/bendlang/bend` at tag `624dd9f` |
| Verilator 5.055 | LGPL-3 (the bundle ships the LGPL text; upstream offers LGPL-3.0 or Artistic-2.0) | `/opt/oss-cad-suite/license/LICENSE.verilator` | `github.com/verilator/verilator` |
| Icarus Verilog 14.0 | GPL-2.0 | `/opt/oss-cad-suite/license/LICENSE.iverilog` | `github.com/steveicarus/iverilog` |
| GTKWave | GPL-2.0+ | `/opt/oss-cad-suite/license/LICENSE.gtkwave` | `github.com/gtkwave/gtkwave` |
| Yosys 0.71+59 | ISC | `/opt/oss-cad-suite/license/LICENSE.yosys` | `github.com/YosysHQ/yosys` |
| SBY, MCY, EQY, nextpnr | ISC (ISC permission text in each file) | `/opt/oss-cad-suite/license/LICENSE.{sby,mcy,eqy,nextpnr}` | `github.com/YosysHQ/…` |
| Z3 | MIT | `/opt/oss-cad-suite/license/LICENSE.z3` | `github.com/Z3Prover/z3` |
| Yices 2.8.0 | BSD-3-Clause | `/opt/oss-cad-suite/share/licenses/yices-2.8.0` | `github.com/SRI-CSL/yices2` |
| Boolector, Bitwuzla | MIT | `/opt/oss-cad-suite/license/LICENSE.{boolector,bitwuzla}` | `github.com/Boolector/…` |
| cvc5 | BSD | `/opt/oss-cad-suite/license/LICENSE.cvc5` | `github.com/cvc5/cvc5` |
| `libc6` (glibc) | LGPL-2.1+ | `/usr/share/doc/libc6/copyright` (prose) | Debian `glibc` source package |
| `libstdc++6`, `libgcc-s1`, `g++` | GPL-3+ with GCC Runtime Library Exception | `/usr/share/doc/gcc-12-base/copyright` (prose; the exception is named) | Debian `gcc-12` source package |
| `make`, `bash`, `coreutils`, `tar`, `gzip`, `libreadline8` | GPL-3+ | each `/usr/share/doc/<pkg>/copyright` | Debian source packages |
| `apt`, `dpkg`, `libapt-pkg6.0` | GPL-2+ | each `/usr/share/doc/<pkg>/copyright` | Debian source packages |
| `libgmp10` | GPL-2+ or LGPL-3+ | `/usr/share/doc/libgmp10/copyright` | Debian `gmp` |
| `libnettle8`, `libhogweed6` | LGPL-3+ or GPL-2+ | their `copyright` files | Debian `nettle` |
| `libcap-ng0`, `libpam0g` | LGPL-2.1+ / BSD-3-clause-or-GPL | their `copyright` files | Debian |
| npm (in the harness image) | Artistic-2.0 | `/usr/local/lib/node_modules/npm/LICENSE` | npm CLI |
| Python 3.12 | PSF-2.0 | `/usr/local/lib/python3.12/LICENSE.txt` | CPython |
| Node.js 20 | MIT | **not in the image** (see gaps) | `nodejs/node` |

The OSS CAD suite already ships 56 per-tool licence files under
`/opt/oss-cad-suite/license/`, so the EDA toolchain's notice texts travel with the
image without anyone assembling them. Debian's `/usr/share/common-licenses/`
carries GPL-1/2/3, LGPL-2/2.1/3, Apache-2.0, BSD, Artistic, CC0 and MPL texts in
every image.

## What publishing would require

The reviewer's checklist, in the order the obligations fall:

1. **Say which images are published.** Today: none. `docker/README.md` rule 1 and
   `THIRD_PARTY.md` both key the obligation to publication, and the `oss-cad-base`
   prerequisite is the one layer that is not meant to be published.
2. **Ship the texts that are missing.** Three gaps, all mechanical:
   - Bend's `LICENSE` is not in the release archive and not in `/opt/bend`; an
     Apache-2.0 distribution must include a copy of the licence.
   - Node.js's MIT licence is absent from the harness image; only npm's
     Artistic-2.0 and corepack's MIT texts are there.
   - The Debian packages whose `copyright` has no machine-readable `License:`
     field still have prose notices; the review should be against the Debian
     source package, not against the image.
3. **Provide corresponding source for the copyleft set.** The GPL-2.0 (Icarus,
   GTKWave) and GPL-3+ (make, bash, coreutils, readline, gcc runtime) components
   need a source reference at the shipped version. The suite is built from a
   pinned release archive and each tool's licence file names its sources; the
   Debian packages have their source package names.
4. **Do not add restrictions** beyond those licences, and do not relicense the
   aggregate. The harness code stays Apache-2.0.
5. **Record the decision** in this file's status line and in `docker/README.md`, so
   the next person can see what was reviewed and when.

## Gaps this inventory found

1. **Bend's licence text is not in the image.** `find /opt/bend -iname 'LICENSE*'`
   returns nothing, and the release archive contains no licence file either. The
   pinned source tree does carry Apache-2.0, so the text exists; it was just never
   copied into the image or the archive.
2. **Node.js's licence text is not in the harness image.** The only licence files
   under `/usr/local` are npm's (Artistic-2.0), corepack's (MIT) and CPython's
   (PSF). Node's MIT text is upstream only.
3. **Half of the Debian layer is not machine-readable.** Counts in the table; the
   load-bearing cases are `libc6` (prose LGPL) and the GCC runtime (prose, with the
   exception), both of which are present but need to be read rather than grepped.
4. **The suite's licence files are per-tool, not per-file.** They name the tool and
   its sources; they do not enumerate the bundled third-party libraries inside
   Yosys (`abc`, `minisat`, `slang`, `symfpu`, …) beyond a list in
   `LICENSE.yosys`. A deeper audit would walk that list; this inventory does not.

## Reproduce

```bash
# packages and their declared licence, from the image itself
docker run --rm -v "$PWD/.bend-cache/lic:/lic" bendeda/oss-cad-base:2026-11-20 /lic/collect.sh

# the EDA toolchain's own licence files
docker run --rm bendeda/oss-cad:2026-11-20 \
  bash -c 'head -4 /opt/oss-cad-suite/license/LICENSE.{yosys,verilator,iverilog,yices}'

# the two images with no licence file for their main component
docker run --rm --entrypoint /bin/bash bendeda/bend:2.0.40 -c 'find /opt/bend -iname "LICENSE*"'
docker run --rm --entrypoint /bin/bash bendeda/harness:0.0.1 -c 'find /usr/local -name "LICENSE*"'

# the GCC runtime exception, and glibc's prose licence
docker run --rm bendeda/oss-cad-base:2026-11-20 \
  bash -c 'grep -c "Runtime Library Exception" /usr/share/doc/gcc-12-base/copyright; head -12 /usr/share/doc/libc6/copyright'
```

The `collect.sh` script is 12 lines: `dpkg-query -W` for the package list, then the
first `License:` line of each `/usr/share/doc/<pkg>/copyright`, with the
architecture suffix stripped because the doc directory does not carry it.
