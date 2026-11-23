# SPDX-License-Identifier: Apache-2.0
# Cookbook S7: refinement relation. The relation is a hypothesis, not a
# definition the checker computes: the law says "if the two states agree, the
# two outputs agree", and the proof is one `Equal.cong` through the output
# function. A real task's relation is a predicate over (model state, RTL state);
# the shape of the proof is the same.
import Base

law cook_s7_flip:
  for a: Bool
  for b: Bool
  for h : {a == b : Bool}
  {Bool.not(a) == Bool.not(b) : Bool}

def cook_s7_flip(a, b, h):
  Equal.cong(Bool, Bool, x => Bool.not(x), a, b, h)
