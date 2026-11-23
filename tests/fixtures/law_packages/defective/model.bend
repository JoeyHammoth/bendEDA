# SPDX-License-Identifier: Apache-2.0
# The model side of the fixture. It is clean on purpose: every finding this
# package produces has to come from the law set or the manifest, and a defect
# here would make the assertion "one seeded defect per rule" untrue.

import Base

def toy_step(x: U32) -> U32:
  U32.add(x, 1)
