# B1: synchronous FIFO

## Interface

| Port | Direction | Width | Meaning |
|---|---|---|---|
| `clk` | input | 1 | clock, rising edge |
| `rst_n` | input | 1 | active-low **synchronous** reset |
| `push` | input | 1 | enqueue request |
| `pop` | input | 1 | dequeue request |
| `din` | input | `W` | data to enqueue |
| `dout` | output | `W` | head of the queue |
| `full` | output | 1 | occupancy equals `D` |
| `empty` | output | 1 | occupancy equals `0` |

Parameters: `W` data width, `D` depth (power of two, `D >= 2`). This package
pins the reduced instance **`W = 32`, `D = 2`** (see `ambiguities.yaml` A2).

## Behaviour

1. On a rising edge with `rst_n` low, occupancy becomes 0 and both flags follow.
   Reset is synchronous: it takes effect on that edge, not immediately.
2. With `push` and not `pop`, and occupancy below `D`, `din` is enqueued and
   occupancy increases by one. With occupancy at `D`, the request is ignored.
3. With `pop` and not `push`, and occupancy above 0, the head is dequeued and
   occupancy decreases by one. With occupancy 0, the request is ignored.
4. With `push` and `pop` together:
   - occupancy 0: the push succeeds and the pop is ignored (occupancy becomes 1,
     and `dout` is `din` on the next cycle);
   - occupancy strictly between 0 and `D`: both succeed, occupancy is unchanged,
     the old head leaves and `din` becomes the last element;
   - occupancy `D`: the pop succeeds and the push is ignored (occupancy becomes
     `D-1`, and the second element becomes the head).
5. With neither `push` nor `pop`, the state does not change.
6. `full` is asserted exactly when occupancy equals `D`; `empty` exactly when
   occupancy equals 0.
7. `dout` shows the oldest element whenever occupancy is above 0. Its value when
   the FIFO is empty is **unconstrained**; nothing may read it then (A1).
8. Elements leave in the order they entered: the first element pushed is the
   first element popped.

## What is deliberately not specified

- The internal storage: registers, a memory macro, or a ring buffer with any
  pointer encoding. Requirement R12 (pointer wrap-around does not corrupt data)
  is a property of the implementation and is covered by conformance and the
  oracle, not by a law (design Appendix B, `conformance_only_requirements`).
- Latency of `full`/`empty` after a push or pop beyond the cycle in which the
  occupancy changes. One cycle of registered output is acceptable **only** if the
  flags are read one cycle after the operation; the specification's cycle-level
  reading in item 6 is the reference.

## Requirements

| ID | Requirement |
|---|---|
| R1 | Occupancy is always in `[0, D]`. |
| R2 | A push when full (with no pop) is ignored. |
| R3 | A pop when empty (with no push) is ignored. |
| R4 | Push and pop together at mid occupancy both succeed; occupancy is unchanged. |
| R5 | Elements are dequeued in enqueue order. |
| R6 | `full` is asserted iff occupancy equals `D`. |
| R7 | `empty` is asserted iff occupancy equals 0. |
| R8 | Reset clears occupancy and both flags. |
| R9 | `dout` is the head whenever occupancy is above 0. |
| R10 | Push and pop together when full: the pop succeeds and the push is ignored. |
| R11 | Push and pop together when empty: the push succeeds and the pop is ignored. |
| R12 | Pointer wrap-around does not corrupt data (conformance-only). |
| R13 | With neither push nor pop, occupancy is unchanged. |
