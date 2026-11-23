# SPDX-License-Identifier: Apache-2.0
# B1 FIFO: the law set. Laws only; the reference proofs are in PROOF_ref.bend and
# the package check composes model.bend + this file + that one into a single
# book. No `import Base` here for the same reason: the composition supplies it,
# and `bendeda law mutate` inlines the model rather than importing it.
#
# Every law is closed over data (a, b, d) and, where the occupancy matters,
# over the level. No law is quantified over a symbolic occupancy: that needs an
# induction this reduced instance does not require, and a law whose proof is
# harder than the property is a liability (LA8). The cost is stated in the
# package README: the transition table is covered row by row, not by one
# quantified induction over occupancy.
#
# Naming and ids follow Appendix G: <task>_<class letter><nn>_<slug>, id
# FIFO-<letter>-<nn>.

# --- occupancy -------------------------------------------------------------

law fifo_s01_count_within_depth:
  for a: U32
  for b: U32
  for level: Level
  {Nat.is_le(count(MkFifo{a, b, level}), 2n) == True{} : Bool}

law fifo_s02_full_iff_count_depth:
  for a: U32
  for b: U32
  for level: Level
  {is_full(MkFifo{a, b, level}) == Nat.is_eq(count(MkFifo{a, b, level}), 2n) : Bool}

law fifo_s03_empty_iff_count_zero:
  for a: U32
  for b: U32
  for level: Level
  {is_empty(MkFifo{a, b, level}) == Nat.is_eq(count(MkFifo{a, b, level}), 0n) : Bool}

# --- push ------------------------------------------------------------------

law fifo_f01_push_empty_count:
  for a: U32
  for b: U32
  for d: U32
  {count(step(MkFifo{a, b, Empty{}}, Push{d})) == 1n : Nat}

law fifo_f02_push_empty_head:
  for a: U32
  for b: U32
  for d: U32
  {dout(step(MkFifo{a, b, Empty{}}, Push{d})) == d : U32}

law fifo_f03_push_half_full:
  for a: U32
  for b: U32
  for d: U32
  {is_full(step(MkFifo{a, b, Half{}}, Push{d})) == True{} : Bool}

law fifo_f04_push_full_noop:
  for a: U32
  for b: U32
  for d: U32
  {count(step(MkFifo{a, b, Full{}}, Push{d})) == 2n : Nat}

# --- pop -------------------------------------------------------------------

law fifo_f05_pop_empty_noop:
  for a: U32
  for b: U32
  {count(step(MkFifo{a, b, Empty{}}, Pop{})) == 0n : Nat}

law fifo_f06_pop_full_count:
  for a: U32
  for b: U32
  {count(step(MkFifo{a, b, Full{}}, Pop{})) == 1n : Nat}

law fifo_f07_pop_full_next_head:
  for a: U32
  for b: U32
  {dout(step(MkFifo{a, b, Full{}}, Pop{})) == b : U32}

# --- simultaneous push and pop --------------------------------------------

law fifo_f08_pushpop_half_count:
  for a: U32
  for b: U32
  for d: U32
  {count(step(MkFifo{a, b, Half{}}, PushPop{d})) == 1n : Nat}

law fifo_f09_pushpop_half_head:
  for a: U32
  for b: U32
  for d: U32
  {dout(step(MkFifo{a, b, Half{}}, PushPop{d})) == d : U32}

law fifo_f10_pushpop_full_head:
  for a: U32
  for b: U32
  for d: U32
  {dout(step(MkFifo{a, b, Full{}}, PushPop{d})) == b : U32}

law fifo_f13_pushpop_empty_head:
  for a: U32
  for b: U32
  for d: U32
  {dout(step(MkFifo{a, b, Empty{}}, PushPop{d})) == d : U32}

# --- reset and idle --------------------------------------------------------

law fifo_f11_reset_empty:
  for a: U32
  for b: U32
  for level: Level
  {is_empty(reset(MkFifo{a, b, level})) == True{} : Bool}

law fifo_f12_idle_preserves_head:
  for a: U32
  for b: U32
  {dout(step(MkFifo{a, b, Full{}}, Idle{})) == a : U32}

# --- witnesses -------------------------------------------------------------
# A witness is a concrete input sequence whose result a closed law states, so
# the checker proves the distinguished state is reachable. Witnesses are not
# task laws: no requirement is scored through them, and the manifest marks them
# L-WIT.

law fifo_w01_reaches_full:
  for d1: U32
  for d2: U32
  {count(step(step(empty_fifo(), Push{d1}), Push{d2})) == 2n : Nat}

law fifo_w02_reaches_empty:
  for d: U32
  {is_empty(step(step(empty_fifo(), Push{d}), Pop{})) == True{} : Bool}

law fifo_w03_reaches_half:
  for d: U32
  {count(step(empty_fifo(), Push{d})) == 1n : Nat}
