# SPDX-License-Identifier: Apache-2.0
# Cookbook S2: case analysis. Bool is the smallest enumeration, so a law over a
# Bool splits into two branches and each branch reduces to `{==}`. Note that the
# branches must be exhaustive: a missing constructor is a `match` failure, not a
# proof obligation the checker reminds you about.
import Base

law cook_s2_and_true:
  for a: Bool
  {Bool.and(a, True{}) == a : Bool}

def cook_s2_and_true(a):
  match a:
    case False{}:
      {==}
    case True{}:
      {==}

law cook_s2_or_false:
  for a: Bool
  {Bool.or(a, False{}) == a : Bool}

def cook_s2_or_false(a):
  match a:
    case False{}:
      {==}
    case True{}:
      {==}

law cook_s2_not_not:
  for a: Bool
  {Bool.not(Bool.not(a)) == a : Bool}

def cook_s2_not_not(a):
  match a:
    case False{}:
      {==}
    case True{}:
      {==}
