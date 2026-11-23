# SPDX-License-Identifier: Apache-2.0
# B1 FIFO: reduced reference model (depth 2, 32-bit data).
#
# The task's parameters are W (data width) and D (depth). This package pins the
# reduced instance W=32, D=2: the smallest depth that exhibits a full queue, a
# head and a second element, so dequeue order is observable. The depth appears
# as the `Level` type rather than as a Nat parameter, because a symbolic Nat
# cannot be decided by the checker without an induction that the reduced instance
# does not need. Level is therefore the occupancy encoding: Empty (0), Half (1),
# Full (2), and `count` decodes it. A depth-parameterised model is open work.
#
# `a` is the head, `b` the second element. Both are always present as data
# registers; the level says whether they are meaningful. `dout` returns `a`, so a
# law about `dout` is a law about the head, and only the laws whose antecedent
# names a non-empty level may compare it.
import Base

type Level is Data:
  Empty{}
  Half{}
  Full{}

type Fifo is Data:
  MkFifo{a: U32, b: U32, level: Level}

type Op is Data:
  Push{din: U32}
  Pop{}
  PushPop{din: U32}
  Idle{}

# Occupancy, decoded from the level.
def count(s: Fifo) -> Nat:
  match s:
    case MkFifo{a, b, level}:
      match level:
        case Empty{}:
          0n
        case Half{}:
          1n
        case Full{}:
          2n

def is_full(s: Fifo) -> Bool:
  match s:
    case MkFifo{a, b, level}:
      match level:
        case Empty{}:
          False{}
        case Half{}:
          False{}
        case Full{}:
          True{}

def is_empty(s: Fifo) -> Bool:
  match s:
    case MkFifo{a, b, level}:
      match level:
        case Empty{}:
          True{}
        case Half{}:
          False{}
        case Full{}:
          False{}

# The head. Only meaningful when the level is not Empty.
def dout(s: Fifo) -> U32:
  match s:
    case MkFifo{a, b, level}:
      a

# One cycle. Reset is separate (`reset`), as in the specification, so `step`
# answers exactly the four interface cases.
def step(s: Fifo, op: Op) -> Fifo:
  match s:
    case MkFifo{a, +b, level}:
      match level:
        case Empty{}:
          match op:
            case Push{din}:
              MkFifo{din, b, Half{}}
            case Pop{}:
              MkFifo{a, b, Empty{}}
            case PushPop{din}:
              MkFifo{din, b, Half{}}
            case Idle{}:
              MkFifo{a, b, Empty{}}
        case Half{}:
          match op:
            case Push{din}:
              MkFifo{a, din, Full{}}
            case Pop{}:
              MkFifo{a, b, Empty{}}
            case PushPop{din}:
              MkFifo{din, b, Half{}}
            case Idle{}:
              MkFifo{a, b, Half{}}
        case Full{}:
          match op:
            case Push{din}:
              MkFifo{a, b, Full{}}
            case Pop{}:
              MkFifo{b, b, Half{}}
            case PushPop{din}:
              MkFifo{b, b, Half{}}
            case Idle{}:
              MkFifo{a, b, Full{}}

def reset(s: Fifo) -> Fifo:
  MkFifo{0, 0, Empty{}}

def empty_fifo() -> Fifo:
  MkFifo{0, 0, Empty{}}
