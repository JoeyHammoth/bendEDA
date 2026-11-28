# What `tf run` has to compute

Issue: LA7 (`bendeda tf run`, Phase 1.7). This note is the design, not the
implementation: `bendeda/cli.py` still routes `tf run` to `_todo`, which exits 3 with
"10k traces per law, verdict agreement". Writing the design first is the point of the
followup — the metric decides the harness, and a harness written before the metric is
a number looking for a definition.

## The metric, as specified

> For each translated law `l` with SVA `s_l`: generate `N_tr = 10,000` random traces
> plus traces from mutated models; compute the verdict of `l` on the Bend model and of
> `s_l` on the corresponding cycle-accurate reference trace; `TF_l = agreement
> fraction`; report mean and minimum over laws. Admission thresholds: mean ≥ 0.999 and
> min ≥ 0.99, plus human review of each translation with agreement kappa ≥ 0.8.

(`bend2-agentic-eda-research-design.md` §10.3, LA7 in Appendix I.) Two things in that
sentence are load-bearing and easy to lose: the unit is **the law**, not the run, and
the quantity is **agreement**, not truth. A translation that is too weak and one that
is too strong are the same size of defect here, and both are disagreements.

## Why the unit is the law

A per-pack number ("the SVA agrees with the model 99.7% of the time") hides the case
that matters: eighteen accurate translations and one that never fires because its
antecedent is unreachable. Averaging is exactly the operation that buries it. So the
report is a row per law — exercised, agreed, disagreed, first disagreement — and the
two summaries (mean, min) are computed over rows that were exercised at all.

The witnesses (`FIFO-W-01..03`) are not rows. They are covers, not claims: the
manifest marks them `L-WIT` and gives `translation_reason`, and a cover has no
verdict to agree with. B1 therefore has 19 rows, not 22.

## The three pieces that do not exist yet

### 1. A per-trace verdict on the model, without a prover

Every law in `LAWS.bend` is closed: its free variables are the `for` binders, and a
trace binds all of them. `fifo_f07_pop_full_next_head` quantifies `a` and `b`; a trace
at a full queue supplies both, because they are the model's state at that cycle.
Instantiated, the law is a ground equation, and its verdict is a boolean that the
compiled model can compute.

That distinction has to survive into the CLI. The **checker** proves the symbolic law
once (`ALL PROOFS CHECK`, LA1); the **compiled model** evaluates one instance of it per
trace. Using `bend` 10,000 times per law would be 190,000 checker invocations to answer
a question the checker already answered symbolically, and it would report per-trace
*proof* where there is per-trace *evaluation*. The pinned JS output from `model.mjs` is
the evaluator the trace gate already relies on (L1's vector path, issue #7), and it is
the right one here.

The trust statement that follows: `tf run` shares the compiler with L1. A compiler bug
that mis-executes `step` moves the model's verdict and not the RTL's, so it shows up as
a disagreement — which is the safe direction — but a bug that mis-executes both sides
of a law identically would not. That is why TF is reported beside the checker's proof
of the source, never instead of it.

### 2. A per-trace verdict on the SVA, at assertion granularity

The pack's assertions are immediate assertions in a clocked block — ordinary
`if (...) assert (...)` in the subset the pinned Yosys parses — so an
assertion-enabled Verilator run of `dut.sv` + `props_locked.sv` over the same stimulus
reports which assertion fired at which cycle. That is the RTL-side verdict, one cycle
at a time, with names.

Not SymbiYosys: 10,000 traces would be 10,000 proofs, and a BMC run over free inputs
answers a different question (does a counterexample exist) than a simulation of one
trace (does this trace violate it). The proof stays the gate's job; the simulation is
the metric's.

One simulation per trace carries every assertion at once, so the cost is 10,000
simulations for the whole law set, not 10,000 × 19. The per-law plan then decides
*which* (cycle, assertion) pairs count as that law's verdict — nothing is re-run to
separate the laws.

### 3. A stimulus recipe per law, declared and reviewable

Uniform random stimulus does not exercise this law set evenly. At depth 2 a random op
stream is full about a third of the time, so most laws get sampled; a depth-8 task
would not, and `fifo_f07` needs `level = Full` *and* `pop` alone *and* a distinguishable
`a ≠ b`. A law the stimulus never exercises contributes vacuous agreement — both sides
"hold" because nothing happened — and a vacuous row is the failure this metric exists to
catch.

So each translated law carries a `fidelity_plan` in `laws.manifest.yaml`'s
`translation` map, beside `sva` and `template`:

```yaml
translation:
  sva: p_pop_full_next_head
  template: miter_ref_model_v1
  fidelity_plan:
    level: Full            # the model state class the law's hypothesis names
    ops: [Pop, PushPop]    # the decoded operations it is about
    observe: [dout]        # the output the law's right-hand side constrains
    window: 1              # cycles from the operation to the observation
    distinct: [a, b]       # binders the stimulus must keep apart to be non-vacuous
```

Three constraints on this format, each with a reason:

- **It is declared, not derived.** The map from a law to its assertion is the
  translation; deriving the plan from the assertion would test the translation against
  itself. The plan is a second, smaller statement of what the law is about — which is
  also what makes it reviewable, and what the kappa in the admission rule is applied
  to.
- **It names model state, not RTL signals.** `level: Full` is the model's `Full{}`;
  `abs.yaml` decides that `count_q == D` means Full. A plan written in RTL signal names
  would bake the abstraction map into the plan and stop being independent of the
  translation it is checking.
- **`distinct` exists because an equality can be satisfied by coincidence.** `dout ==
  second_d` holds trivially when both are zero; `fifo_f07` is only exercised when the
  trace keeps `a ≠ b`. This is the same defect the corpus found in the locked pack
  (two variants passed it because the ordering law read the design's own register), one
  layer down.

`bendeda law translate` is the command that emits the plan (§9's CLI table says so:
"emit TF test plan"); `tf run` consumes it. Until `law translate` exists, `tf run` has
nothing to read that it did not invent.

## What the report says, and what it must refuse to say

```json
{
  "task": "B1_fifo",
  "traces": 10000,
  "seed": 20261128,
  "laws": [
    {"id": "FIFO-F-07", "sva": "p_pop_full_next_head",
     "exercised": 3012, "agreed": 3012, "disagreed": 0, "tf": 1.0},
    {"id": "FIFO-F-10", "sva": "p_pushpop_full_head",
     "exercised": 0, "agreed": 0, "disagreed": 0, "tf": null,
     "note": "the plan's stimulus never reached Full with a push/pop pair"}
  ],
  "tf_mean": null,
  "tf_min": null,
  "exit": 1
}
```

- `tf` is `null`, not `1.0`, when `exercised` is 0, and a `null` row makes the run's
  verdict a failure rather than a pass on the rows that did run. A metric that divides
  by zero and calls the quotient perfect is the stub's failure mode with arithmetic.
- A disagreement is reported with the trace id and the cycle, so it can be replayed
  with `bendeda`'s existing determinism: same seed, same trace, same two verdicts.
- The exit codes follow the gate convention already in place: 0 thresholds met, 1 below
  threshold (a finding about the package), 3 not implemented. `tf run` today exits 3,
  and this note is what a later implementation has to satisfy to exit 0.

## What this does not measure

- **Unreachable cells.** A translation that omits `PushPop` entirely, and a plan that
  never asks for `PushPop`, agree perfectly on every trace both are given. `tf run`
  cannot see the hole; the plan's review is what closes it. This is why the admission
  rule pairs the numeric thresholds with a human kappa: TF bounds the translation's
  behaviour where it was exercised.
- **Mutated-model traces.** The definition includes them. They need the mutant model
  compiled and its verdicts computed — the mutation report already exists
  (`bendeda law mutate`), the compiled mutant does not. First implementation can run
  random traces only and say so in the report rather than silently claim the full
  definition.
- **Multi-cycle laws.** `bv/OPEN.md` defers the FSM helpers `step`, `run` and
  `trace_equal` to Phase 1 (tracked under BendBV, #8) because Bend 2.0.40 has no
  polymorphic fold usable across state types. Every B1 law is one-step, so the plan's
  `window` is `1` throughout and a `run`-based law (`L-LIVE-k`, `L-PROT`) cannot yet be
  stated, let alone translated. The plan format carries `window` from day one so that
  the first multi-cycle law does not need a format change.
- **Vacuity of the RTL side.** Whether an assertion's antecedent is reachable under the
  assumptions is VR, a separate metric in §10.3. `tf run` reports `exercised` on the
  *model* side; conflating the two would let an unreachable assertion pass as
  untested-but-fine.

## Order of work

1. `laws.manifest.yaml` gains `translation.fidelity_plan` for B1's 19 transferable
   laws, and lint L011 checks its shape (known level, operation and signal vocabulary,
   non-empty `ops` and `observe`, `window ≥ 1`). This is documentation plus one rule, and
   it can land before any simulator runs.
2. A per-trace model evaluator: one `model.mjs` compile, N evaluations, a row per
   (law, trace) with the verdict and the binders it used. Testable without Docker.
3. An assertion-observing bench over the pack: Verilator with assertions enabled,
   reporting `(assertion, cycle)` pairs for one trace. Testable against the corpus — the
   known-bad variants must fire the assertion the corpus already names.
4. `tf run` joins the two and reports. The first real number it can produce is B1's,
   and the corpus's ten behaviourally broken entries are the negative control: a TF of
   1.0 on an entry the pack rejects is a defect in the plan, not a faithful translation.

Steps 1 and 2 do not need Verilator or Docker; step 3 does. That split is deliberate:
the metric's definition should be pinned and lintable before a container is involved, so
that a disagreement found later is about a translation and not about a build.

**Status (2026-11-28).** Steps 1 and 2 are in. Step 1:
`tasks/seq/B1_fifo/laws.manifest.yaml` declares a `fidelity_plan` for all 19 translated
laws, and L011 validates the shape of any plan a package declares (it does not require
one yet, because nothing reads a plan and the corpora carry copies of the manifest).

Step 2: `bendeda/tf.py` renders one judge per law from the law's own claim, compiles the
module once, and evaluates it per cycle through `tools/law_eval.mjs`. The plan gates the
rows, so an invariant is checked at every cycle while `fifo_f04` is checked only on `Full`
with a push (287 of 8,000 cycles in the recorded run). Against the reference model every
law is exercised and none disagrees; a model whose pop-from-full returns the design's head
instead of the second element is caught by FIFO-F-07 and by no other law. FIFO-F-11 is
evaluated on every pre-state, because `reset` is a model function and not a trace
operation; the RTL side will need `rst_n` actually asserted to observe it (step 3).

Steps 1 and 2 produce no TF number, because a number computed from one side is agreement
with itself.

**Step 3 (2026-11-28).** `bendeda/tf_rtl.py` compiles the pack with Verilator's
`--assert -DFORMAL` in the pinned `oss-cad` image and runs one trace per process,
reporting the assertion Verilator names and the cycle the pack judged. Against the
corpus: `as_shipped` is clean over an eight-cycle trace, `m01_pop_keeps_count` fires
`p_pop_full_count` at trace cycle 2, and `v06_lifo_shift` fires
`p_pop_full_next_head` at cycle 2 — the assertions the corpus already names, read
from the simulator's own message rather than from a second statement of the pack.
`tests/test_tf_rtl.py` holds that, and its Docker-backed test skips with the reason
where the image is absent.

Two limits carry into step 4. A failed assertion stops the simulation, so a trace
yields at most its first `(assertion, cycle)` pair; separate processes keep each
trace's first failure its own. And `p_reset_empty` needs `rst_n` asserted mid-run,
which the trace alphabet does not yet produce, so FIFO-F-11 would be an unexercised
row — a `null`, not agreement — until a reset is part of the stimulus.

`tf run` still exits 3 until step 4 joins the two sides.
