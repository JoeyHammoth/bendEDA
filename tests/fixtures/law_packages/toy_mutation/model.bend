# SPDX-License-Identifier: Apache-2.0
# The model side of the mutation fixture. It exists to be mutated: two sites,
# both of which a law in LAWS.bend must notice.

import Base

def toy_step(x: U32) -> U32:
  U32.add(x, 1)
