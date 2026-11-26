# SAT_counter: a saturating counter

A fixture, not a study task. It exists so one submission carries both things the
visible gates judge: RTL and a model for `trace`, and a law package for `lint`.
The RTL, port manifest and stimulus plan are `experiments/fixtures/toy_counter`'s;
the laws, manifest and provenance sidecar are this directory's addition.

## Interface

| Port | Direction | Width | Meaning |
|---|---|---|---|
| `clk` | input | 1 | clock, rising edge |
| `rst` | input | 1 | active-high **synchronous** reset |
| `en` | input | 1 | count enable |
| `inc` | input | 4 | increment |
| `c` | output | 4 | the count |

## Behaviour

1. On a rising edge with `rst` high the count becomes 0.
2. Otherwise, with `en` high, the count becomes `min(c + inc, 15)`; with `en` low
   the count is unchanged.

## Requirements

| ID | Requirement |
|---|---|
| R1 | The count never exceeds its ceiling, 15. |
| R2 | Below the ceiling, one enabled cycle adds `inc` exactly. |
| R3 | An enabled cycle whose sum lands exactly on the ceiling gives 15. |
| R4 | A zero increment leaves the count unchanged. |

Reset is not a requirement: the model here is `step` over a U32 count with no
reset state, so a law about reset would have nothing to compare it with. The
trace gate judges reset against the RTL directly, because its stimulus plan
starts from a reset cycle.

## Why the laws are closed over literals

A law quantified over a symbolic U32 (`step(c, 1) == ...`) needs an arithmetic
induction over `U32.is_gt` that the checker does not give for free, and a law
whose proof is harder than the property is a liability (LA8 in the design's law
gate set). Every law in `LAWS.bend` is therefore stated at a literal, which is
what makes it close by evaluation — the same trade-off `tasks/seq/B1_fifo`
records for its occupancy.
