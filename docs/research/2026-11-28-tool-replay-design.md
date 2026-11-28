# What replaying a tool result has to record

Issue #15, `Remaining`: "model calls and tool results in the replay". This note is the
design decision that issue asks for before code: whether to re-execute a tool or to
replay a recorded result, who records it, and what "reproduced" means when the tool is
not deterministic.

`docs/policy-proxy.md` states the gap in one line: `replay` covers the proxy's
decisions, and RF needs the tool results too.

## The metric, as specified

> **RF** (Replay Fidelity): fraction of runs whose scored outcome is reproduced when
> tool results are replayed from logs.

(`bend2-agentic-eda-research-design.md` §10.3, the metric table.) The unit is **the
run**, not the call. A run whose 200 calls all replay but whose submission differs is
a run that was not reproduced, and averaging per-call agreement would hide it.

## What exists, and the first defect this note found

- `bendeda/replay.py` re-decides the proxy's audit log and prints the first sequence
  number that diverges. Exit 0 / 1 / 3, and a `budget` refusal is re-derived from the
  declared allowance rather than counted as a policy disagreement.
- `bendeda/score.py` recomputes `S` from the log, and takes `V`/`O` from the gate and
  oracle results the harness recorded. `gate run` re-executes the visible gates.
- The proxy's `AuditLog` writes one line per decision:
  `{"seq", "tool", "resource", "action", "rule", "reason"}`.
- `bendeda/schemas/event.schema.json` describes `events.jsonl` differently: it
  **requires** `t`, `run_id`, `seq`, `actor`, `type`, allows `tool_call` and
  `tool_result`, and says *"Args and results are hashed as well as stored so a replay
  can detect tampering."*

Those are two shapes under one filename. The schema promises `args_sha256` and
`result_sha256`; the writer produces neither. That has to be settled first, because
"replay the results" is not definable against a log that has no result field.

## Why not re-execute the tool

Re-execution answers a different question. It measures whether the tool is
deterministic now, not whether the log is sufficient to reproduce the run. Three
concrete failures:

- **Some tools cannot be re-executed.** The oracle is on another host; the agent's
  network is internal by construction. A metric that needs a live oracle cannot be
  computed on the machine that holds the bundle.
- **Some tools legitimately differ.** A compiler embeds paths and timestamps; a model
  server samples. Re-execution diverges on runs that were correctly logged, and RF
  would report the tool's entropy as a replay defect.
- **It is already someone else's job.** `gate run` re-executes the gates on the
  submitted artifacts. That is `V`, and it is measured. RF is a claim about the log.

So: **record and replay**. Re-execution stays as a separate determinism check — the
`FR`-shaped question — and is not folded into RF.

## What a record has to contain

Per call, in order:

| Field | Why |
|---|---|
| `seq`, `run_id`, `actor`, `type: tool_call` | identifies the call and who made it |
| `tool`, `resource`, `args_sha256` (+ args, or a reference) | the request the result answers |
| the proxy's `policy` block | the decision the call was made under; replay already checks it |
| `type: tool_result`, `result_sha256`, `status`, `elapsed_ms` | the answer, and that it is the one recorded |
| a byte store reference | a digest detects tampering; only the bytes replay |

Store the bytes in a content-addressed `results/<sha256>` directory beside
`events.jsonl`, with a size cap. A result above the cap is a **refusal at record
time** — not a hash-only line that replays as "tampered or missing" later.

Who records it: not the agent. An agent that writes its own `tool_result` can write a
result it did not receive, and the whole point is that the log is evidence. The proxy
sees every call and is the only process that sees all of them, so the result belongs
to the proxy — which means the proxy must *serve* the tool call, not only allow it.
That is the missing component, and it is the same transport `bendeda serve`
(`bend-mcp`, `hdl-mcp`) is reserved for. Until it exists, a result recorded by the
arm's driver is testimony with a digest, and RF computed from it inherits that.

## What "reproduced" means

Four levels, each with its own name so a report cannot blur them:

1. **Decision replay** (exists). Every logged decision follows from the policy.
2. **Call-sequence replay.** The re-run makes the same `(tool, resource)` calls in the
   same order. A different order is a divergence at the first call that differs.
3. **Result replay.** Each call is answered from `results/<sha256>`, and the digest
   matches the line.
4. **Outcome replay.** The same submission digest and the same `S`/`V` (and `O`,
   where the host that holds the pack reproduces it) come out.

RF is level 4 over runs that recorded at least one tool call:

```
RF = |runs where submission_sha256 and S,V match on replay| / |runs with recorded calls|
```

A run with no recorded calls is **`null`**, not `1.0`. A command-only cell has no tool
results to replay, and counting it as faithful is the stub's error with arithmetic —
the same rule `bendeda/tf.py` applies to an unexercised law.

A divergence is reported by class and sequence number, so it can be replayed:

| Class | What it means |
|---|---|
| `decision` | the policy no longer produces the logged decision (today's report) |
| `sequence` | the re-run called a different tool or resource at this `seq` |
| `result` | the recorded result is missing, or its digest does not match |
| `submission` | the same results produced a different submission |
| `verdict` | the same submission scored differently through the gates |

## What this does not measure

- **The model's calls.** A re-run that samples differently makes different calls. That
  is a `sequence` divergence about the log, not evidence that the original score was
  wrong — which is why `run.json` pins the model, its seed and temperature, and why RF
  is reported only over runs whose calls matched.
- **`O` off-host.** The oracle pack is scored where it is decrypted (§5.4). RF over
  `S`/`V` is computable here; `O` is reproduced on the host and recorded through
  `oracle score`, so a bundle missing that answer is not counted.
- **The truth of a result.** Replay checks that the recorded answer is the one used
  again, not that the tool was right. `V` and `O` are the claims about correctness.
- **Nondeterminism of the tool.** Recording makes the run reproducible; it does not
  make the tool deterministic. Comparing a re-execution against the record is a
  different metric and needs its own definition.

## Order of work

1. **One event format.** Fold the proxy line into `event.schema.json` (`t`, `run_id`,
   `actor`, `type`, the `policy` block) and add `args_sha256`/`result_sha256` where the
   schema already promises them; update `AuditLog` and `replay` together, with a test
   that a line written by the proxy validates against the schema. This is the piece
   that makes the rest definable.
2. **Make the proxy the recording point.** It gains the tool transport (or fronts the
   MCP servers), returns the result, and writes both lines. A result the proxy did not
   return is not a result.
3. **Store the bytes.** `results/<sha256>`, capped, refused above the cap; the bundle
   carries the directory and the manifest lists it.
4. **`replay --results <bundle>`.** Serve the recorded results in order to a re-run of
   the arm's command, then compare submission digest and `S`/`V`. Exit 0 reproduced,
   1 a divergence with its class and `seq`, 3 nothing to replay.
5. **Report RF.** `run` writes `rf` per cell and RF over the matrix, `null` when a cell
   recorded no calls.

Steps 1 and 3 are testable without an agent loop: a fixture arm that makes three
recorded calls can be replayed through a stub transport. Step 4 needs step 2 to be
real, and step 2 is where the first measurable RF comes from. Until then, the honest
report is the one `policy-proxy.md` already gives: decisions replay, outcomes do not.

## What this changes elsewhere

- `bendeda/schemas/event.schema.json` is currently a promise the writer does not keep.
  Either the proxy writes it or the schema describes the other file — the note's step 1
  chooses the first.
- `docs/policy-proxy.md`, "What does not exist yet", first bullet: after this note the
  gap has a name, a format and an order, and the next change is step 1 rather than a
  discussion.
