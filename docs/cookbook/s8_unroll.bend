# SPDX-License-Identifier: Apache-2.0
# Cookbook S8: bounded unrolling. For small k, unfold `run` by reducing the
# literal and discharge the resulting fixed number of steps. Unrolling is honest
# only while k is small and written in the law; it does not prove the law for
# every k, and a task that needs that needs induction instead.
import Base

def cook_s8_run(k: Nat, s: Bool) -> Bool:
  match k:
    case 0n:
      s
    case 1n+p:
      cook_s8_run(p, Bool.not(s))

law cook_s8_not_not:
  for a: Bool
  {Bool.not(Bool.not(a)) == a : Bool}

def cook_s8_not_not(a):
  match a:
    case False{}:
      {==}
    case True{}:
      {==}

law cook_s8_two_steps:
  for s: Bool
  {cook_s8_run(2n, s) == s : Bool}

def cook_s8_two_steps(s):
  # `2n` reduces to `Succ{Succ{Zero}}`, so the run unfolds to
  # `cook_s8_run(0n, Bool.not(Bool.not(s)))`, and the lemma closes it.
  cook_s8_not_not(s)
