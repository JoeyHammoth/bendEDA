# SPDX-License-Identifier: Apache-2.0
# Toy reference model for the L1 vector path (issue #7).
#
# Not a study task: it exists to prove the plumbing — Bend compiles this file to
# an ES module, a Node driver feeds it stimulus, and a comparator detects a
# one-cycle offset. A real task package under tasks/ has laws; this does not.
#
# Behaviour: a 4-bit saturating counter.
#   step(count, inc) = min(count + inc, 15)
#   run(xs, count)   = step folded over xs

import Base

# Two constants so the driver can check that Nat and U32 cross the JS boundary.
def limb() -> U32:
  15

def pick(c: Bool, x: U32) -> U32:
  match c:
    case True{}:
      15
    case False{}:
      x

def step(+count: U32, +inc: U32) -> U32:
  pick(U32.is_gt((count + inc : U32), 15), (count + inc : U32))

def run(xs: List<U32>, count: U32) -> U32:
  match xs:
    case Nil{}:
      count
    case Con{h, t}:
      run(t, step(count, h))
