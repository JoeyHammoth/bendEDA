# SPDX-License-Identifier: Apache-2.0
# Negative control for B1. This is the law Appendix G.9 asks for: plausible, and
# false on the model. It must be refused, with both values printed. It is not in
# LAWS.bend and has no manifest entry, so nothing scores it.
#
# Composed with model.bend by tests/test_b1_fifo.py.
law fifo_n01_strict_below_depth:
  for a: U32
  for b: U32
  {Nat.is_lt(count(MkFifo{a, b, Full{}}), 2n) == True{} : Bool}

def fifo_n01_strict_below_depth(a, b):
  {==}
