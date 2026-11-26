# SPDX-License-Identifier: Apache-2.0
# SAT_counter: laws over the fixture's saturating counter.
#
# The model is `step(count, inc) = min(count + inc, 15)` over U32 (model.bend).
# Every law is closed over literals: a law quantified over a symbolic U32 needs
# an induction over `U32.is_gt` that the checker does not close for free, and a
# law whose proof is harder than the property is a liability. The cost is stated
# in spec.md: the ceiling is covered at its two boundaries and at one exact fit,
# not quantified over the whole range.
#
# Naming and ids follow Appendix G: <task>_<class letter><nn>_<slug>, id
# SAT-<letter>-<nn>.

# --- the ceiling ------------------------------------------------------------

law counter_s01_never_above_ceiling:
  {step(15, 1) == 15 : U32}

law counter_s02_ceiling_holds_under_max_increment:
  {step(15, 15) == 15 : U32}

# --- the sum when it fits ---------------------------------------------------

law counter_f01_sum_when_it_fits:
  {step(3, 4) == 7 : U32}

law counter_f02_exact_fit_reaches_ceiling:
  {step(14, 1) == 15 : U32}

law counter_f03_zero_increment_preserves_count:
  {step(7, 0) == 7 : U32}

# --- witnesses --------------------------------------------------------------
# A witness is a concrete input sequence whose result a closed law states, so the
# checker shows the distinguished state is reachable. The manifest marks them
# L-WIT: no requirement is scored through them.

law counter_w01_reaches_ceiling:
  {step(step(step(0, 5), 5), 5) == 15 : U32}

law counter_w02_reaches_zero:
  {step(0, 0) == 0 : U32}

law counter_w03_reaches_mid:
  {step(0, 5) == 5 : U32}
