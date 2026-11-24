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

## What does not exist yet

These are the rest of #15 and they are the reason the issue stays open:

- **Budget accounting**, and therefore the `S=0` (exhausted) versus `excluded`
  (infrastructure) distinction. Nothing in a log today can score that.
- **Whole-run replay.** `replay` checks the proxy's decisions, not gate results,
  model calls or the scored outcome.
- **The container plumbing** — no route to the oracle volume, no network except the
  proxy, and the mount list that makes both true. Until that exists, the proxy is
  the enforcement point by convention, not by construction, and no document should
  say otherwise.

## Why replay at all

A log is testimony until someone recomputes from it. The property that makes a
recorded run usable is that its decisions follow from the policy that was in force,
and that is a computation anyone can repeat with the same two files. Measuring that
on hand-built fixtures first keeps the tool honest before it is pointed at a real
run.
