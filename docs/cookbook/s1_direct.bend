# SPDX-License-Identifier: Apache-2.0
# Cookbook S1: direct computation. Closed goals that reduce to a literal
# equality. The proof is `{==}`; if it fails, the claim is false or a definition
# name is wrong, and the diagnostic says which.
import Base

law cook_s1_and_eval:
  {U32.and(12, 10) == 8 : U32}

def cook_s1_and_eval():
  {==}

law cook_s1_shl_eval:
  {U32.shln(1, 4n) == 16 : U32}

def cook_s1_shl_eval():
  {==}

law cook_s1_add_wrap_eval:
  {U32.add(4294967295, 1) == 0 : U32}

def cook_s1_add_wrap_eval():
  {==}

law cook_s1_nat_eval:
  {Nat.add(2n, 3n) == 5n : Nat}

def cook_s1_nat_eval():
  {==}
