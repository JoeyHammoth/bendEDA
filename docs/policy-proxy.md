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

What `plan` does **not** do is start the pair. The commands it prints are the ones
run by hand above; wiring them into a subcommand with lifecycle handling is the next
step, and until it exists `plan` writing to stdout is the only claim it makes.

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

## What does not exist yet

- **Starting the sandbox from the CLI.** `plan` prints; the containers above were run
  by hand. Lifecycle, teardown and the proxy's readiness are not implemented.
- **Whole-run replay and scoring.** `replay` checks the proxy's decisions, not gate
  results, model calls or the scored outcome, and `classify` returns an unscored
  outcome when the budget held.
- **The mount list as a guarantee rather than a check.** `check` reads a running
  container; it cannot stop a different one from being started without the mount
  allowlist. That belongs with the CLI lifecycle above.

## Why replay at all

A log is testimony until someone recomputes from it. The property that makes a
recorded run usable is that its decisions follow from the policy that was in force,
and that is a computation anyone can repeat with the same two files. Measuring that
on hand-built fixtures first keeps the tool honest before it is pointed at a real
run.
