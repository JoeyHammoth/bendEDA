# Third-party components and licences

Nothing here is vendored. Tools are installed from upstream inside pinned
container images, or fetched at run time, and their versions are recorded in
every run (`run.json`) and every design bundle (`manifest.json`).

This table is the Phase 0 licence-audit artefact required by §8 step 0.2. Rows
marked **⚠ unverified** are recalled rather than confirmed and must be checked
before the pinned images are built; a row that cannot be verified is either
replaced or marked optional.

## Language under test

| Tool | Role | Licence | Status |
|---|---|---|---|
| Bend 2 (`bendlang/bend`) | Laws, models, proofs | Apache-2.0 | ⚠ confirm in repository `LICENSE` at the pinned release |
| `bend2-lsp` | Editor support | unknown | optional; not used by the pipeline |

## EDA toolchain

| Tool | Role | Licence | Status |
|---|---|---|---|
| OSS CAD Suite (bundle) | Distribution of the tools below | mixed open source | shipped as a pinned release, build files published |
| Yosys | Synthesis | ISC | ⚠ confirm |
| SymbiYosys (`sby`) | BMC, k-induction, PDR | ISC | ⚠ confirm |
| `eqy` | Equivalence checking | ISC | ⚠ confirm |
| MCY | Mutation coverage | ISC | ⚠ confirm |
| Verilator | Simulation, lint | LGPL-3.0 / Artistic-2.0 | ⚠ confirm |
| Icarus Verilog | Simulation | GPL-2.0 | ⚠ confirm; separate process, not linked |
| nextpnr | Place-and-route *reports* only | ISC | ⚠ confirm |
| Z3 / Bitwuzla / cvc5 / Yices | SMT back ends | MIT / BSD | used via `sby`, not linked |
| Verible | Lint, format | Apache-2.0 | ⚠ confirm |
| Lean 4 + Sparkle HDL | Comparator arm C5, Track D | Apache-2.0 / ⚠ | optional |
| KiCad + `kicad-cli`, SKiDL | Track C only | GPL-3.0 / MIT | optional; Track C is exploratory |

## Python and harness

| Package | Role | Licence |
|---|---|---|
| cpython | Runtime | PSF-2.0 |
| cocotb | Testbenches | BSD-3-Clause |
| pytest / Hypothesis (optional) | Test tooling | MIT / MPL-2.0 |
| statsmodels, SciPy, pandas | Analysis | BSD-3-Clause |
| matplotlib | Plots | PSF-based (matplotlib licence) |
| `mcp` Python SDK | MCP servers | MIT |
| `age` (optional) | Oracle encryption | BSD-3-Clause |

The harness itself uses the standard library where it can. Any new runtime
dependency needs a licence note in the pull request that adds it.

## Benchmarks and data

| Dataset | Use | Redistribution |
|---|---|---|
| CVDP (`NVlabs/cvdp_benchmark`) | Calibration only | **not redistributed**; fetched at run time |
| VerilogEval, RTLLM, RTL-Repo | Calibration only | **not redistributed**; fetched at run time |

## Models

Model weights are never distributed by this project. For each model used, the
run record stores the identifier, digest, licence name and the provider terms in
force on the run date. Generated outputs are published only where the model's
licence permits it, and that permission is recorded per model.

## Container images

If prebuilt images are ever published, they must ship the upstream licence texts
and source references for every GPL/LGPL component they contain. Until then only
Dockerfiles and build scripts are published, which keeps the obligation with the
consumer who builds the image.
