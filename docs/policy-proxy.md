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
  which is not a pass.

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

## What does not exist yet

- **Gate re-execution.** `V` is read from the results the harness recorded; `gate run`
  is still a planned command, so nothing here re-runs a gate on submitted artifacts.
- **Model calls and tool results in the replay.** `replay` covers proxy decisions; the
  design's full RF needs the tool results replayed too.
- **The mount allowlist as an independent guarantee.** `up` builds the single mount
  into the argv and `check` refutes a live container, but neither can stop a different
  container being started outside this CLI.

## Why replay at all

A log is testimony until someone recomputes from it. The property that makes a
recorded run usable is that its decisions follow from the policy that was in force,
and that is a computation anyone can repeat with the same two files. Measuring that
on hand-built fixtures first keeps the tool honest before it is pointed at a real
run.
