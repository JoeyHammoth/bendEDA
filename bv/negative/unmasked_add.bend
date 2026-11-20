# SPDX-License-Identifier: Apache-2.0
# Negative control for BendBV (issue #8).
#
# This is the library with mask(w) deleted from the addition: the one defect the
# mask exists to prevent. The claim is the same 8-bit wrap the library proves,
# so the control is only meaningful next to it: masked add claims 44 and is
# right, unmasked add claims 44 and is wrong.
#
# `bend bv/negative/unmasked_add.bend` must print SOME PROOFS FAIL. A gate that
# accepted this file would be accepting a bit-width bug.

import Base

def bv_add_unmasked(a: U32, b: U32) -> U32:
  U32.add(a, b)

law bv_add_unmasked.wrap8:
  {bv_add_unmasked(200, 100) == 44 : U32}

def bv_add_unmasked.wrap8():
  {==}
