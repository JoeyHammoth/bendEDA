# SPDX-License-Identifier: Apache-2.0
# Cookbook S4: inductive invariant. State a predicate over reachable states,
# prove it at reset, and prove it is closed under `step`. The step proof carries
# the predicate as a hypothesis; the branch that would break it is discharged by
# the hypothesis itself, because after unfolding the goal *is* the hypothesis.
import Base

type CookMode is Data:
  Idle{}
  Armed{}
  Fired{}

def cook_next(m: CookMode) -> CookMode:
  match m:
    case Idle{}:
      Idle{}
    case Armed{}:
      Idle{}
    case Fired{}:
      Fired{}

def cook_live(m: CookMode) -> Bool:
  match m:
    case Idle{}:
      True{}
    case Armed{}:
      True{}
    case Fired{}:
      False{}

law cook_s4_init:
  {cook_live(Idle{}) == True{} : Bool}

def cook_s4_init():
  {==}

law cook_s4_step:
  for m: CookMode
  for h : {cook_live(m) == True{} : Bool}
  {cook_live(cook_next(m)) == True{} : Bool}

def cook_s4_step(m, h):
  match m:
    case Idle{}:
      {==}
    case Armed{}:
      {==}
    case Fired{}:
      # `cook_live(Fired{})` reduces to False{}, so the goal is `False{} == True{}`
      # — exactly the hypothesis, which is why this branch is not provable from
      # nothing. If the hypothesis were absent this case would fail.
      h
