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

`--out <path>` writes the full per-control report, which now carries an
`environment` block: the checker, and — when it runs in a container — the digest
the daemon resolved plus the version the image reports. A local source run says
`image: none (local source pin)` instead of borrowing a digest it never used.
At this pin `--verdict` exits 3
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
because each mutant costs one checker run per law. Its `--out` report carries the
same `environment` block as `canary`. The catalogue and its limits
are in `docs/research/2026-11-24-law-lint.md`.

The catalogue mutates arithmetic *and* table structure: sibling `match` arms that
bind the same names are exchanged, a nullary constructor is replaced by another of
its type, and a bare numeric literal on its own line (`2n` as a match arm's whole
body) is bumped. A package that keeps `LAWS.bend` and `PROOF_ref.bend` apart
must pass a composed file, because `--laws` names one file and a law with no proof
is recorded as an error, not as a kill:

```bash
cat tasks/seq/B1_fifo/LAWS.bend tasks/seq/B1_fifo/PROOF_ref.bend > /tmp/laws.bend
bendeda law mutate tasks/seq/B1_fifo/model.bend --laws /tmp/laws.bend --local
```

## The proof cookbook

`docs/proof_cookbook.md` is the guide the agent gets before it writes a proof:
the syntax that checks at the pin, nine worked strategies (S1-S9) and the
diagnostics table. The examples are `docs/cookbook/*.bend`, and every one is run
by the test suite against Bend 2.0.40:

```bash
python tools/fetch_bend.py
export BENDEDA_BUN=bun
export BENDEDA_BEND_CLI=.bend-cache/bend-2.0.40/bend2/main.ts
python -m unittest tests.test_cookbook -v
```

Eight files must print `ALL PROOFS CHECK`; `s9_counterexample.bend` must print
`SOME PROOFS FAIL` with both values, because a cookbook with no false example is
not teaching the failure mode. The proof escape hatches (PEH-01..PEH-07) are in
`bendeda/laws/peh.py` and are what `law lint` reports.

## The sealed oracle

```bash
bendeda oracle seal path/to/oracle --recipient age1... --out oracle_sealed  # dry run first:
bendeda oracle seal path/to/oracle --dry-run
bendeda oracle verify-commitment path/to/oracle --commitment oracle_sealed/commitment.json
```

`seal` writes a deterministic archive, a Merkle commitment over every component
and a `SHA256SUMS` for the ciphertext; it refuses rather than writing a
plaintext archive. `verify-commitment` needs no key and no decryption, because
the commitment is built over the plaintext before encryption:

| Code | `seal` | `verify-commitment` |
|---|---|---|
| 0 | sealed, or dry run printed | the root matches |
| 1 | encryption failed | a component differs; both roots printed |
| 3 | no recipient, no `age`, unreadable input — nothing sealed | no directory, no commitment, unreadable commitment |

On the scoring host, `oracle score` does both halves in one step: it refuses a pack that
no longer matches the published commitment, runs the pack's own `score.py` over the
bundle, and records the answer through the same checks as `oracle record`:

```bash
bendeda oracle score --pack path/to/oracle/pack \
  --commitment oracle_sealed/commitment.json \
  --bundle .bend-cache/run/b1-c0-s1 --host scoring-1
```

The pack's `score.py` is called as `score.py <bundle>` with the pack as its working
directory, and prints `{"components": {"name": true}}`. A crash, a timeout, output that
is not JSON, or a component that is not a boolean is exit 3 with nothing written.

`O` is scored on the scoring host, and the result comes back as data rather than as a
claim:

```bash
bendeda oracle record --bundle .bend-cache/run/b1-c0-s1 \
  --components components.json --host scoring-1 \
  --commitment oracle_sealed/commitment.json
```

`components.json` maps each pack component to a boolean. The command writes `oracle.json`
carrying the host and the pack's Merkle root, so `score` can compute `O` without trusting
a number typed into prose. It refuses a void bundle, a bundle that already scored `S=0`
(zero is already the answer) and a bundle that already carries a result — a second score
is a disagreement, not an update. Exit 3 means nothing was written.

The canary GUID in `oracle_sealed/canary.txt` is refused in any file under
`tasks/` by `tools/check_oracle_absence.py`. Details:
`docs/research/2026-11-24-sealed-oracle.md`.

## The policy proxy and decision replay

```bash
bendeda proxy serve --policy policy.json --events .bend-cache/run/events.jsonl --port 8765
bendeda proxy decide --policy policy.json --tool fs-read --resource oracle/b1/checks.md
bendeda replay --events .bend-cache/run/events.jsonl --policy policy.json
```

The proxy answers allow/deny for every tool call and writes one JSONL line per
decision, including the rule that fired. It is deny-by-default, every deny rule is
tried before any allow rule, and resources are normalised so `tasks/../oracle/x`
cannot match `tasks/**`. `proxy decide` exits 0 when the call is allowed and 1 when
it is refused, which makes it usable in a script.

`replay` re-decides the log against the policy: 0 every recorded decision follows
from it, 1 a decision does not (the sequence number and both rules are printed), 3
there was nothing to replay. It replays the proxy's decisions, not a scored run: budgets are
enforced and scored by `score`, and replaying tool results and model calls is the rest of
[#15](https://github.com/JoeyHammoth/bendEDA/issues/15); `docs/policy-proxy.md` states
what is missing.

## The sandbox: plan, up, check, down

```bash
bendeda runner plan --workspace tasks --policy tests/fixtures/proxy/policy.json \
  --events .bend-cache/events/run.jsonl     # prints docker commands, starts nothing
bendeda runner up   --workspace tasks --policy tests/fixtures/proxy/policy.json \
  --events .bend-cache/events/run.jsonl     # network, then proxy, then agent
bendeda runner check bendeda-agent --workspace tasks --oracle oracle_sealed
bendeda runner down
```

`runner up` creates an internal network, starts the proxy on it, waits for the proxy's
`/health`, and only then creates the agent container, whose single bind mount is the
workspace. Any failure tears down what started, so a failed `up` leaves no agent
without its proxy. `runner check` inspects a live container and exits 1 naming each
problem: another network, host networking, a mount that is not the workspace, or a
mount that contains the oracle. `runner down` removes both containers and the network;
something already gone is not a failure. Before creating anything, `up` asks the image for
its copy of `bendeda` and compares it with the checkout: a harness image built before your
last change would otherwise fail inside the sandbox as `unrecognized arguments`, which
reads like a bug in the command rather than a stale image. `BENDEDA_SKIP_IMAGE_CHECK=1`
overrides the check deliberately.

## Budgets and the score

```bash
bendeda runner classify --events .bend-cache/events/run.jsonl --max-calls 400
bendeda score --bundle .bend-cache/run/b1-c0-s1 --policy policy.json
```

`runner classify` exits 0 always — it reports, it does not judge. The verdicts are
`within budget` (`scored`, no score yet), `exhausted` (`scored`, score 0.0) and
`excluded` (not scored, re-run), and an infrastructure failure outranks exhaustion.

`score` turns a run directory into the design's three verdicts: `S` (submitted before
exhaustion or crash), `V` (every visible gate passed, checked against
`run.json.visible_gates`) and `O` (every oracle component passed). Exit codes are part
of the contract:

| Code | Meaning |
|---|---|
| 0 | scored and complete |
| 1 | the tool log does not follow from its policy |
| 2 | excluded — infrastructure failed, re-run; **not** a zero |
| 3 | incomplete — a gate or oracle result is missing, which is not a pass |

A gate with no recorded result leaves `V` null and the run incomplete rather than
letting `all([])` report a pass. The directory holds `events.jsonl` (required),
`run.json` (budgets and `visible_gates`), `gates.json`, `oracle.json` and optionally
an `outcome.json` to reproduce.

## Gates, the arm's command, and the matrix

```bash
bendeda gate run trace --artifacts experiments/fixtures/toy_counter --out gates.json
bendeda gate run formal --artifacts docker/smoke
bendeda runner exec --submit tasks/seq/B1_fifo/submission -- python -m bendeda --version
bendeda run --matrix experiments/matrices/smoke.json --dry-run
bendeda run --matrix experiments/matrices/smoke.json --limit 1
```

`gate run` re-executes a gate on what the arm submitted and exits 0 pass, 1 fail, 3 a
gate could not run (a missing compiler or image is a skip, never a pass). `trace`
compiles the submitted model, simulates the submitted RTL and requires every cycle to
agree; the same task with wrapping RTL fails at cycle 7. `formal` runs every `*.sby` job
and requires a PASS marker.

`runner exec` runs the arm's command inside the sandbox started by `up`. `--submit`
records a submission through the proxy afterwards; the policy has to permit `submit`, or
the run cannot score `S=1`.

`--max-calls` turns the budget into an enforcement rather than a report. The proxy
(`proxy serve --max-calls N`) refuses the call after the allowance with `429` and
`rule: budget`, and `runner exec --events <log> --max-calls N` polls the log and kills
the sandbox as the backstop for work the proxy never sees (`--wall-min` covers a command
that makes no calls at all). A matrix cell hands its own `budgets` to both, so
`budget_exhausted: true` in `cell.json` means the sandbox was actually stopped. Exit 0 is
deliberate — a spent allowance is a result, and the log then scores `S=V=O=0`.

A matrix may declare `"order": { "method": "hash-v1", "seed": 7 }`. `hash-v1` sorts each
cell label by `sha256("<seed>:<label>")` — reproducible on any machine, with no RNG state
to reproduce — and interleaves arms. `run` prints the prereg hash and writes
`prereg.json` beside the bundles, so a run says which order it executed and which
declaration it belonged to.

`run --matrix` expands a matrix, runs each cell in the sandbox, re-executes the declared
gates and leaves `events.jsonl`, `gates.json`, `expected.json`, `score.json` and
`cell.json` per cell. It exits 3 while `O` is absent: the oracle pack is scored on the
scoring host with `oracle score`, so the cell is incomplete here rather than green.

| Code | `gate run` | `run --matrix` |
|---|---|---|
| 0 | every gate passed | every cell complete |
| 1 | a gate failed | a cell failed to execute |
| 3 | a gate could not run | cells incomplete (no oracle verdict yet) |

## What is planned, and where

| Command | Issue |
|---|---|
| `tf run` | blocked by BendBV ([#8](https://github.com/JoeyHammoth/bendEDA/issues/8)) |
| `conformance` (L2/L3 rungs) | arrives with the EDA image ([#6](https://github.com/JoeyHammoth/bendEDA/issues/6)) |
| `gate calibrate` | Phase 1.7 — GS/GSp over the bug corpus; `gate run` and `run` exist |
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
