# SPDX-License-Identifier: Apache-2.0
# A law that pins the model's arithmetic. Both catalogue mutants of model.bend
# (add -> sub, and 1 -> 2) change what this law claims, so both must be killed.

import Base

law toy_s01_step:
  for x: U32
  {toy_step(x) == U32.add(x, 1) : U32}

def toy_s01_step(x):
  {==}
