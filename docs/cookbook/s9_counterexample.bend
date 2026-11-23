# SPDX-License-Identifier: Apache-2.0
# Cookbook S9: counterexample report. This file is deliberately FALSE and is the
# one example the cookbook expects to be refused. Run it to see the diagnostic a
# false law produces, then write the counterexample into the report instead of
# changing the law.
#
# U32 arithmetic wraps, so `4294967295 + 1` is 0, not 4294967295.
import Base

law cook_s9_bad_wrap:
  {U32.add(4294967295, 1) == 4294967295 : U32}

def cook_s9_bad_wrap():
  {==}
