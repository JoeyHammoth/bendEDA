# Running the CLI

## Install

```bash
git clone https://github.com/JoeyHammoth/bendEDA
cd bendEDA
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Python 3.12+. No network is needed after install; no EDA toolchain is required for the commands that currently work.

## Verify the install

```bash
bendeda --version        # bendeda 0.0.1
bendeda validate --all   # schemas + task packages
python -m unittest discover -s tests -v
```

## The exit-code contract

| Code | Meaning |
|---|---|
| `0` | the command did what it says |
| `1` | a check ran and failed |
| `2` | usage error |
| `3` | **not implemented** — the command printed its plan and refused to pretend |

Exit `3` is load-bearing. In a study about false assurance, a stub that exits `0` would let a person or an agent believe a gate ran when nothing ran. If a script needs to distinguish states, test for `0` explicitly rather than treating "no exception" as success.

## What works today

```bash
bendeda init --dry-run
bendeda task new B1_fifo --tier B --dry-run
bendeda validate --all
bendeda --help

# L1 vector path (needs bun + the pinned compiler source)
python tools/fetch_bend.py
export BENDEDA_BEND_CLI=.bend-cache/bend-2.0.40/bend2/main.ts
bendeda conformance compile --model experiments/fixtures/toy_counter/model.bend --out .bend-cache/out/model.mjs
bendeda conformance trace --module .bend-cache/out/model.mjs --cycles 24
bendeda conformance trace --module .bend-cache/out/model.mjs --cycles 24 --inject-offset 1
```

The last command is a self-test of the comparator: it shifts the DUT by one cycle
and the gate passes only if the offset is *detected*. A trace checker that cannot
see a one-cycle shift is measuring nothing.

To judge real RTL rather than the Python reference, run the DUT under Verilator in
the pinned image (needs Docker; the image is `bendeda/oss-cad:2026-11-20`):

```bash
# the testbench is generated from dut.json — a port manifest, not hand-written code
bendeda conformance trace --module .bend-cache/out/model.mjs --cycles 24 \
  --dut verilator --rtl experiments/fixtures/toy_counter/dut.sv \
  --spec experiments/fixtures/toy_counter/dut.json

# the negative control: wrapping RTL must fail as a value mismatch
bendeda conformance trace --module .bend-cache/out/model.mjs --cycles 24 \
  --dut verilator --rtl experiments/fixtures/toy_counter/dut_wrap.sv; echo "exit=$?"
```

A plan can drive each input separately. `incs` stays the model's stimulus; the
`stimulus` object maps an input name to its own sequence:

```json
{
  "incs": [1, 2, 3],
  "stimulus": { "inc": [1, 2, 3], "en": [1, 1, 0] }
}
```

```bash
bendeda conformance trace --module .bend-cache/out/model.mjs \
  --dut verilator --rtl experiments/fixtures/toy_counter/dut.sv \
  --spec experiments/fixtures/toy_counter/dut.json \
  --plan path/to/plan.json
```

## The checker canary suite

```bash
python -m bendeda canary --local                       # pinned sources under Bun
python -m bendeda canary --image pinned                # released binary in the image
python -m bendeda canary --local --verdict --only a01   # proven-kernel checker
```

32 negative controls, 4 positive ones, each declaring the stage it must be
refused at. Exit codes:

| Code | Meaning |
|---|---|
| 0 | every control landed where it was declared |
| 1 | a false accept, a false reject, or a control refused at the wrong stage |
| 3 | no checker could run, so nothing was measured — not a pass |

`--out <path>` writes the full per-control report. At this pin `--verdict` exits 3
because the BendTT kernel needs Lean v4.34.0; the record is in
`docs/research/2026-11-23-checker-canary.md`.

## Law authoring gates

```bash
bendeda law lint tasks/seq/B1_fifo                       # rules L001-L015
bendeda law mutate tasks/seq/B1_fifo --out mut.json       # LA3, pinned image by default
bendeda law lint tasks --recursive --mutation mut.json    # L006 from the mutation report
```

`law lint` exit codes: 0 every applicable rule ran and found nothing, 1 a rule
fired or a package could not be read, 3 no task package was found. A rule that
needs metadata the package does not carry says so (`L004 not evaluated: ...`,
`L006 not evaluated: ...`) instead of leaving the report looking clean.

`law mutate` exit codes: 0 at least 20 mutants, kill rate at least 0.9 and no law
surviving every mutant; 1 below any of those; 3 no checker or no mutable site.
`--local` uses the pinned sources under Bun, and `--max-mutants` caps a run
because each mutant costs one checker run per law. The catalogue and its limits
are in `docs/research/2026-11-24-law-lint.md`.

## What is planned, and where

| Command | Issue |
|---|---|
| `oracle seal`, `oracle verify-commitment` | [#13](https://github.com/JoeyHammoth/bendEDA/issues/13) |
| `tf run` | blocked by BendBV ([#8](https://github.com/JoeyHammoth/bendEDA/issues/8)) |
| `conformance` (L2/L3 rungs) | arrives with the EDA image ([#6](https://github.com/JoeyHammoth/bendEDA/issues/6)) |
| `gate run`, `gate calibrate`, `run`, `replay` | [#15](https://github.com/JoeyHammoth/bendEDA/issues/15) |
| `report`, `bundle verify`, `serve` | Phase 6 / Phase 2 |

## Common friction

- **`ModuleNotFoundError: bendeda`** — the package is not installed; run `pip install -e .` from the repository root.
- **Windows line endings** — the repository normalises to LF via `.gitattributes`. If `tools/check_whitespace.py` complains after an editor round-trip, your editor wrote CRLF.
- **A gate says "skipped"** — a required image or capability is absent. Skipped is not a pass; CI treats it as such and prints the reason.
- **Tests pass but a command exits 3** — intended, see the table above.

## Where the docs are

- Site: <https://joeyhammoth.github.io/bendEDA/>
- This wiki for the plan and decisions
- Design document for anything normative
