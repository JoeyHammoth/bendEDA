# SPDX-License-Identifier: Apache-2.0
# B1 FIFO: reference proofs (RPA artifact).
#
# Every law in LAWS.bend has exactly one same-name proof here, and the package
# composes model.bend + LAWS.bend + this file into one book before checking. The
# proof is `match` on the level where the level is symbolic, and `{==}` where the
# goal is a closed computation: the model is a transition table over a finite
# occupancy type, so the checker's normaliser does the work and none of these
# laws needs induction.
#
# No escape hatch appears here: no `@unsafe`, no hole, no foreign body. The
# proofs are short because the laws are stated over the reduced instance; if a
# law were restated over a symbolic Nat, the proof would need the induction that
# `Nat.is_le` does not give for free.

def fifo_s01_count_within_depth(a, b, level):
  match level:
    case Empty{}:
      {==}
    case Half{}:
      {==}
    case Full{}:
      {==}

def fifo_s02_full_iff_count_depth(a, b, level):
  match level:
    case Empty{}:
      {==}
    case Half{}:
      {==}
    case Full{}:
      {==}

def fifo_s03_empty_iff_count_zero(a, b, level):
  match level:
    case Empty{}:
      {==}
    case Half{}:
      {==}
    case Full{}:
      {==}

def fifo_f01_push_empty_count(a, b, d):
  {==}

def fifo_f02_push_empty_head(a, b, d):
  {==}

def fifo_f03_push_half_full(a, b, d):
  {==}

def fifo_f04_push_full_noop(a, b, d):
  {==}

def fifo_f05_pop_empty_noop(a, b):
  {==}

def fifo_f06_pop_full_count(a, b):
  {==}

def fifo_f07_pop_full_next_head(a, b):
  {==}

def fifo_f08_pushpop_half_count(a, b, d):
  {==}

def fifo_f09_pushpop_half_head(a, b, d):
  {==}

def fifo_f10_pushpop_full_head(a, b, d):
  {==}

def fifo_f13_pushpop_empty_head(a, b, d):
  {==}

def fifo_f11_reset_empty(a, b, level):
  {==}

def fifo_f12_idle_preserves_head(a, b):
  {==}

def fifo_f14_idle_preserves_count(a, b, level):
  match level:
    case Empty{}:
      {==}
    case Half{}:
      {==}
    case Full{}:
      {==}

def fifo_f15_pushpop_empty_count(a, b, d):
  {==}

def fifo_f16_pushpop_full_count(a, b, d):
  {==}

def fifo_w01_reaches_full(d1, d2):
  {==}

def fifo_w02_reaches_empty(d):
  {==}

def fifo_w03_reaches_half(d):
  {==}
