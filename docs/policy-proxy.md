# The policy proxy and decision replay (issue #15, first increment)

The proxy is the process that holds the socket, and it is where "the agent has no
network" can be true rather than promised. A library inside the agent would be a
rule the agent can decline to call.

## What exists

```console
$ bendeda proxy serve --policy policy.json --events .bend-cache/run/events.jsonl --port 8765
proxy: listening on http://127.0.0.1:8765, default deny, 4 rule(s), events -> .bend-cache/run/events.jsonl

$ curl -s -X POST localhost:8765/call -H 'Content-Type: application/json' \
    -d '{"tool": "fs-read", "resource": "oracle/b1/checks.md"}'
{"decision": {"action": "deny", "allowed": false, "reason": "...", "rule": "deny-oracle"}, ...}
```

- **Deny by default.** A call that matches no rule is refused with `rule: default`.
- **Deny wins.** Every deny rule is tried before any allow rule, so a broad allow
  cannot shadow a specific deny. The cost is that exceptions to a deny need the
  deny narrowed rather than shadowed.
- **Paths are normalised before matching.** `tasks/../oracle/x` would match
  `tasks/**` textually and reach the oracle, so it is resolved first and refused
  when it leaves the workspace, as are absolute paths.
- **Every decision is one line** in an append-only JSONL log, allowed or not, with
  the rule that fired. A malformed request is a 400 and is not logged as a decision.
- **`bendeda replay --events ... --policy ...`** re-decides the log and prints the
  sequence number of the first difference. Exit 0 means every recorded decision
  follows from the policy; 1 means one did not; 3 means there was nothing to replay,
  which is not a pass. A `budget` refusal is the proxy's ceiling rather than the
  policy's decision, so `--max-calls` supplies the allowance the run declared and the
  refusal must be exactly the call the ceiling fired on; without it that line is
  reported as undecidable instead of being counted against the policy.

## The runner: one mount, one network

`bendeda runner plan` prints the sandbox and starts nothing. `bendeda runner check`
inspects a running container and reports every way it is not the sandbox the issue
asks for: attached to another network, attached to host networking, mounting anything
besides the workspace, or mounting a directory that contains the oracle.

```console
$ bendeda runner plan --workspace tasks --policy tests/fixtures/proxy/policy.json \
    --events .bend-cache/events/run.jsonl
$ bendeda runner check bendeda-agent-demo --workspace tasks --oracle oracle_sealed
runner check: bendeda-agent-demo is attached only to bendeda-offline and mounts only .../tasks
$ echo $?
0
```

Measured against a live pair of containers on `docker network create --internal`:

```
agent: urllib.request.urlopen('http://github.com')  → blocked: URLError (name resolution)
agent → proxy: fs-read seq/B1_fifo/spec.md   → 200, rule read-workspace
agent → proxy: fs-read ../oracle_sealed/x    → 403, rule escape
```

The same check on the repository root instead of `tasks/` fails, correctly: the
oracle is inside that mount, so it is reachable. Getting that verdict right needed
two fixes found by running it — Docker Desktop reports a bind source as `/c/Users/...`
on some calls and `C:/Users/...` on others, and Git Bash's `/c/...` had to be
converted before `Path.resolve()` turned it into `C:\c\...`.

`plan` starts nothing; `up` runs exactly those commands, in the order that makes the
proxy the only egress, and `down` removes them:

```console
$ bendeda runner up --workspace tasks --policy .bend-cache/demo/policy.json \
    --events .bend-cache/demo/events.jsonl
runner up: started network, proxy, agent on bendeda-offline
runner up: the agent mounts only tasks and reaches only the proxy
$ echo $?
0

$ docker exec bendeda-agent python -c "urllib.request.urlopen('http://github.com')"
urllib.error.URLError: <urlopen error [Errno -3] Temporary failure in name resolution>
$ <proxy call: fs-read seq/B1_fifo/spec.md>      → 200
$ <proxy call: fs-read ../oracle_sealed/x>       → HTTPError 403: Forbidden

$ bendeda runner down
runner down: removed the agent, the proxy and the network bendeda-offline
```

Every failure path in `up` tears down before it raises. That is not tidiness: an
agent container that exists without its proxy is the one state worse than no sandbox,
and it is reachable by any step failing after the agent started. The proxy must also
answer `/health` before the agent is created at all, which caught a real problem on
the first run — the harness image predated `proxy serve`, so it exited 2, and the
readiness gate refused to hand an agent a sandbox whose only egress was dead.

## Budgets: exhaustion is a result, failure is not

`bendeda runner classify` turns a proxy log into one of three verdicts:

| Verdict | `scored` | `score` | Meaning |
|---|---|---|---|
| within budget | true | null | the gates decide the score |
| exhausted | true | **0.0** | the arm used its allowance; that is a result |
| excluded | false | null | infrastructure failed; re-run, do not score |

```console
$ bendeda runner classify --events .bend-cache/events/run.jsonl --max-calls 1
{"scored": true, "score": 0.0, "reason": "budget exhausted after 2 calls", "calls": 2}
```

Exclusion beats exhaustion: an event with `tool: "infra"` invalidates the budget
reading too, so a crashed daemon cannot be recorded as a zero-scoring arm.

### Enforcing it, not only reporting it

The allowance is enforced where every call passes: `proxy serve --max-calls N` refuses
the call after the allowance with `429` and logs it with `rule: budget`, so an arm cannot
spend past its budget at all.

```console
$ <first call, one-call allowance>    → 200, rule read-workspace
$ <second call>                       → HTTP 429
{"action": "deny", "rule": "budget", "reason": "budget exhausted after 1 call(s)", ...}
```

`runner exec --events <log> --max-calls N [--wall-min M]` adds the backstop: it polls the
log and kills the sandbox when the count passes, which covers a command that spawns work
the proxy never sees. `--wall-min` covers one that makes no calls at all.

Polling alone is not enough, and the first live run showed it: three calls went through a
one-call allowance before a 0.5 s poll noticed. The `429` closes that window; the kill
closes the one the `429` cannot see. A matrix cell hands its `budgets` to both.

Exit 0 from `runner exec` is deliberate: a spent allowance is a result, not a harness
failure, and the log then classifies as `exhausted`, so `score` records `S=V=O=0`.

## Scoring: `S`, `V` and `O`

`bendeda score --bundle <dir>` computes the three verdicts the design document
defines (§5.4), from a run directory holding `events.jsonl` and, when they exist,
`run.json`, `gates.json`, `oracle.json` and an `outcome.json` to compare against.

| Symbol | 1 iff | Source |
|---|---|---|
| `S` | the agent submitted before exhaustion or a crash | the event log, via `budget.classify` |
| `V` | `S=1` and every gate in the arm's visible set passed | `gates.json`, checked against `run.json.visible_gates` |
| `O` | `S=1` and every oracle component passed | `oracle.json` |

```console
$ bendeda score --bundle .bend-cache/demo/bundle --policy .bend-cache/demo/policy.json
{
  "scored": true, "S": 1, "V": 1, "O": 1, "complete": true,
  "reason": "submitted; all 2 visible gates passed; all 2 oracle components passed",
  "replay": {"events": 2, "matched": 2, "malformed": [], "diverged": [], "ok": true},
  "outcome_reproduced": null
}
$ echo $?
0

$ bendeda score --bundle .bend-cache/demo/excluded      # an infra event, not a zero
{"scored": false, "S": null, "V": null, "O": null, "complete": false,
 "reason": "infrastructure failure: daemon: docker"}
$ echo $?
2
```

| Exit | Meaning |
|---|---|
| 0 | scored and complete |
| 1 | the tool log does not follow from its policy, so the outcome is not evidence |
| 2 | excluded: infrastructure failed, re-run; this is not a zero |
| 3 | incomplete: a gate or oracle result is missing, which is not a pass |

`all([])` is true, and that is what makes this module worth writing: a gate with no
recorded result is compared against the arm's declared set first, so a partial record
is incomplete (exit 3) rather than silently green. `V` and `O` stay `null` instead of
borrowing a zero.

Passing `--policy` also re-decides the log, so a bundle whose decisions diverge exits
1 before anyone reads its score. Passing `outcome.json` adds `outcome_reproduced`
(the ingredient for the design's Replay Fidelity metric): a recorded outcome that does
not follow from the log is reported, while the score still comes from the log.

## Gates that execute (`V`)

`bendeda gate run` fills the `Gate` protocol in `bendeda/plugins/interfaces.py`: a gate
reads the artifact directory an arm submitted, runs the pinned toolchain on it, and
returns pass or fail with the evidence that decided it. A missing capability is `skip`,
and a skip is never written to `gates.json`.

| Gate | Passes iff | Fails iff |
|---|---|---|
| `trace` | the model compiles, the submitted RTL simulates, and every cycle agrees | a required file is missing, the model does not compile, the DUT errors, or any cycle disagrees |
| `formal` | every `*.sby` job writes a PASS marker | there is no `.sby` job, a job exits non-zero, or it finishes without PASS |
| `lint` | the law package passes rules L001-L015 and carries no finding | the package is missing, the linter reports a finding, or a `mutation.json` it was given cannot be read |

```console
$ bendeda gate run trace --artifacts experiments/fixtures/toy_counter --out gates.json
gate trace: pass
gate run: wrote gates.json

$ bendeda gate run trace --artifacts .bend-cache/wrap      # the same task, wrapping RTL
gate trace: fail — model and DUT disagree at cycle 7
$ echo $?
1

$ bendeda gate run formal --artifacts docker/smoke
gate formal: pass
```

Two translations are needed, and both are in the code with the reason: a plan written
against the model names `incs`, while the generated testbench wants one sequence per
input port (for a single-input design they are the same sequence); and `load_plan`
normalises a missing `stimulus` section to `{}`, so "absent" has to be tested as empty.

## Calibration: GS and GSp (LA4)

`gate run` says what one submission did; `gate calibrate` says what the gate set is
worth. It runs the gates over a corpus and reports gate sensitivity (the share of bugs
some gate rejected) and gate specificity (the share of correct implementations accepted):

```console
$ bendeda gate calibrate --corpus experiments/corpus/toy_counter
gate calibrate: toy_counter from experiments/corpus/toy_counter, gates trace
  correct/golden                     accepted    trace: pass
  ...
  per gate:
    trace      caught 6 bug(s), 6 of them alone; rejected 0 correct implementation(s)
gate calibrate: GS 1.000 (mutant 1.000 3/3, seeded 1.000 3/3), GSp 1.000 (3/3 correct)
$ echo $?
0
```

A corpus is a `corpus.json` naming one or more base directories, a gate set and one entry
per variant; each entry directory holds only the files it replaces, so a bug is a one-file
diff against a design that already passes, and `calibrate` stages the bases in order and
then the entry over them in a temporary directory. More than one base is how a study
task's package is combined with a submitted RTL directory: the laws come from the task
and the implementation from the submission. `mutant` and `seeded` are reported apart because the design reports
them apart: a gate that catches only the hand-written half is not calibrated.

An entry whose gate skipped is *undecidable*: excluded from the rate and listed.
Counting it as a miss would blame the gate for a machine with no simulator; counting it
as a catch would invent a result. An undecidable entry, or fewer than `--min-correct`
decidable correct implementations, exits 3 — not calibrated — even when the partial rates
look perfect. Exit 1 is calibrated and failing: a surviving bug, a rejected correct
implementation, or GS below `--min-gs` (0.95, LA4's floor).

A rate for the union is not a rate for the members, so the run reports what each gate
decided: bugs it caught, how many of those it caught alone (it was the only thing between
that bug and an accept), and correct implementations it rejected. A gate that caught
nothing is named as inert. It does not fail the run by itself — a gate can be right to
pass a corpus it was not built to catch — but a gate set that is only as good as its
strongest member is not the set the design claims.

`lint` is the second implemented gate, and the one a law package is judged by. It runs
rules L001-L015 over the submitted `LAWS.bend` and `laws.manifest.yaml` and passes only
on no finding, quoting the rule that fired (`L012 ...: priority is None`). The linter
ships with the harness, so this gate has no missing capability to skip for: a submission
without a law package is a failure that names the missing manifest, not a skip.
`experiments/corpus/b1_fifo_laws` calibrates it over the shipped B1 FIFO package — GS and
GSp 1.000, each seeded defect caught by the rule it was seeded for.

A submission may carry `mutation.json` beside its manifest; that is the report L006
reads, and without it the linter says `L006 not evaluated` rather than reporting a clean
package it never checked for model sensitivity. A report the linter cannot parse is a
failure naming the file, because a submission that carries evidence nobody can read has
not been judged on it. `experiments/corpus/toy_counter_laws` is the corpus that names
both `trace` and `lint`, so the `per gate:` table has two gates answering on the same
entries — its seeded `s01_law_survives` entry supplies a report in which every law
survived the mutant, and L006 fails it.

A gate cannot hold a calibration entry forever either. Every simulated container is
named, and a timeout removes it: killing the `docker` client stops the client, not the
daemon's process, and that process keeps the bind mount busy. On a timeout, or when the
client cannot start at all, the harness runs `docker rm -f` before reporting, so a hung
simulation is a failure that names its limit instead of a hung harness. `--sim-timeout`
sets that limit per run for `gate run` and `gate calibrate` (default 900s); it is the
gate's own deadline, so the calibration ends when it expires rather than when the
simulation finally returns.

## `runner exec`: the arm runs inside the sandbox

`up` leaves a keepalive container; `runner exec` runs the arm's command in it and can
record the submission through the proxy:

```console
$ bendeda runner exec --submit tasks/seq/B1_fifo/submission -- python -m bendeda --version
bendeda 0.0.1
```

The submission is posted from inside the container, because the host reaches neither the
internal network nor the proxy. `submit` must be permitted by the policy: a run policy
without that rule cannot produce `S=1`, and a refusal is recorded rather than counted as
a submission — the first matrix run scored `S=1` off a *denied* submit, which is exactly
the kind of green that has to be caught by running the thing.

Where the CLI lives is not cosmetic either. The harness image used to keep the package at
`/work`, which the runner mounts the workspace over, so `python -m bendeda` answered `No
module named bendeda` inside a sandbox whose purpose is to run it. The image now carries
the package at `/opt/bendeda` and leaves `/work` to the agent.

Both containers run as the invoking user, not as the image's uid 10001: the workspace and
the events directory are bind mounts owned by the caller, so the proxy's log and the
arm's artifacts would otherwise be files the host can neither read nor clean up. The
proxy hit that first (it answered `/health`, which touches no file, and then could not
record a call), and the arm has the same problem in the other direction once it writes
`/work`. The sandbox's boundary is the single mount and the internal network, not the uid
inside it; Windows has no uid, so it keeps the image user.

## The run matrix

```console
$ bendeda run --matrix experiments/matrices/smoke.json --dry-run
{"n": 1, "cell": "C0-toy_counter-s1", "task": "toy_counter", "arm": "C0", "seed": 1}
run: 1 cell(s) in smoke; nothing was executed

$ bendeda run --matrix experiments/matrices/smoke.json --limit 1
{"O": null, "S": 1, "V": 1, "cell": "C0-toy_counter-s1", "complete": false, "error": null}
run: 1 cell(s), 0 complete, 1 incomplete
$ echo $?
3
```

Each cell starts a sandbox, runs `command` inside it, records the submission, tears the
sandbox down, re-executes the declared gates on the artifacts, and writes `events.jsonl`,
`gates.json`, `expected.json`, `score.json` and `cell.json` under `--out/<matrix>/<cell>`.
Exit 3 is the honest verdict: `S` and `V` are complete and `O` is not, because the oracle
pack is scored on the scoring host. That answer comes back through `bendeda oracle score
--pack <dir> --commitment <json> --bundle <cell> --host <name>` (or `oracle record` when
the host scores by other means), which writes `oracle.json` with the host and the pack's
Merkle root and refuses a void bundle, a bundle that already scored `S=0`, and a bundle
that already carries a result.

`run` also prints the matrix's prereg hash and writes `prereg.json` next to the
bundles. The hash covers every declared field with defaults folded in; `order`
(`declared`, or `hash-v1` with a seed) fixes the sequence by `sha256("<seed>:<label>")`,
so the order is reproducible without an RNG and interleaves arms.

## What does not exist yet

- **Model calls and tool results in the replay.** `replay` covers proxy decisions; the
  design's full RF needs the tool results replayed too. The decision — record and
  replay, not re-execute — and the record format are
  `docs/research/2026-11-28-tool-replay-design.md`, which also names the first defect
  to fix: `bendeda/schemas/event.schema.json` promises an event log with
  `args_sha256`/`result_sha256`, while the proxy writes a line the schema does not
  describe.
- **Running the oracle pack here.** `run` cannot compute `O`; it stays absent until the
  scoring host's answer is recorded. `oracle score` now does that on the host that holds
  the decrypted pack — it verifies the pack against the commitment, runs the pack's
  `score.py` and records the result — but nothing in this repository runs the pack itself,
  so a cell here is incomplete rather than scored on a verdict nobody computed.
- **The mount allowlist as an independent guarantee.** `up` builds the single mount
  into the argv and `check` refutes a live container, but neither can stop a different
  container being started outside this CLI.
- **A wall-clock guarantee for a silent command.** `--wall-min` has a real-process test
  (`tests/test_runner.py` sleeps past a 1.2-second allowance and is killed), but it is
  still polled, so a command that blocks the poller is outside what it measures.

## Why replay at all

A log is testimony until someone recomputes from it. The property that makes a
recorded run usable is that its decisions follow from the policy that was in force,
and that is a computation anyone can repeat with the same two files. Measuring that
on hand-built fixtures first keeps the tool honest before it is pointed at a real
run.
