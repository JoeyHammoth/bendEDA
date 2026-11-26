# SPDX-License-Identifier: Apache-2.0
# SAT_counter: reference proofs. Every law in LAWS.bend has one same-name def
# here, and the package composes model.bend + LAWS.bend + this file into a single
# book before checking.
#
# The proofs are `{==}` because every law is closed over literals: the checker's
# normaliser evaluates `step` on the literal arguments and the goal becomes an
# equality between two values. A law quantified over a symbolic U32 would need
# the induction over `U32.is_gt` that spec.md says this fixture deliberately
# avoids. No escape hatch appears here: no `@unsafe`, no hole, no foreign body.

def counter_s01_never_above_ceiling():
  {==}

def counter_s02_ceiling_holds_under_max_increment():
  {==}

def counter_f01_sum_when_it_fits():
  {==}

def counter_f02_exact_fit_reaches_ceiling():
  {==}

def counter_f03_zero_increment_preserves_count():
  {==}

def counter_w01_reaches_ceiling():
  {==}

def counter_w02_reaches_zero():
  {==}

def counter_w03_reaches_mid():
  {==}
