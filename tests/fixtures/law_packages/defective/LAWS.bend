# SPDX-License-Identifier: Apache-2.0
# A law set with one seeded defect per lint rule L001-L015.
#
# Nothing here is compiled: this package exists so `law lint` has a fixture set
# in which every rule must fire. `tests/test_law_lint.py` asserts that the set
# of reported rules is exactly the set the fixture seeds, so adding a rule
# without seeding it fails the test rather than passing quietly.

import Base

law toy_s01_count_le_depth:
  for c: U32
  {U32.add(c, 1) == c : U32}

def toy_s01_count_le_depth(c):
  {==}

law toy_f01_guard_unsat:
  for a: U32
  for h : {0n == 1n : Nat}
  {U32.add(a, 2) == a : U32}

def toy_f01_guard_unsat(a, h):
  {==}

law toy_s02_extra_in_file:
  for a: U32
  {U32.add(a, 3) == a : U32}

def toy_s02_extra_in_file(a):
  {==}

law toy_bad_name_9x:
  for a: U32
  {U32.mul(a, 2) == a : U32}

def toy_bad_name_9x(a):
  {==}

law toy_s05_conjunction:
  for a: U32
  for b: U32
  {Bool.and(U32.add(a, b) == U32.add(b, a), Bool.and(a, b) == a) : Bool}

def toy_s05_conjunction(a, b):
  {==}

law toy_s06_left_comm:
  for a: U32
  for b: U32
  {U32.sub(a, b) == U32.sub(b, a) : U32}

def toy_s06_left_comm(a, b):
  {==}

law toy_s07_renamed_comm:
  for x: U32
  for y: U32
  {U32.sub(x, y) == U32.sub(y, x) : U32}

def toy_s07_renamed_comm(x, y):
  {==}

law toy_s08_unchecked:
  for a: U32
  {U32.add(a, 4) == a : U32}

@unsafe
def toy_s08_unchecked(a):
  {==}

law toy_s10_unknown_symbol:
  for a: U32
  {U32.frobnicate(a) == a : U32}

def toy_s10_unknown_symbol(a):
  {==}

law toy_f02_no_translation:
  for a: U32
  {U32.add(a, 5) == a : U32}

def toy_f02_no_translation(a):
  {==}

law toy_s11_no_priority:
  for a: U32
  {U32.add(a, 6) == a : U32}

def toy_s11_no_priority(a):
  {==}

law toy_f03_no_requirements:
  for a: U32
  {U32.add(a, 7) == a : U32}

def toy_f03_no_requirements(a):
  {==}
