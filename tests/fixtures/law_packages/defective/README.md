# Defective law package (lint fixture)

One seeded defect per rule L001-L015, all in one package. `tests/test_law_lint.py`
asserts that the set of rules `bendeda law lint` reports is exactly the set below,
so a rule that stops firing fails the test.

| Rule | Seeded in |
|---|---|
| L001 | `toy_f01_guard_unsat`: a conditional law with no witness |
| L002 | `toy_s02_extra_in_file` (no manifest entry); `toy_s03_absent_from_file` (no law) |
| L003 | `toy_f03_no_requirements`: `requirements: []` |
| L004 | requirement `R3` is covered by no law and not declared conformance-only |
| L005 | `toy_f01_guard_unsat`: hypothesis `{0n == 1n : Nat}` |
| L006 | `mutation.json`: `toy_s01_count_le_depth` was killed by no mutant |
| L007 | `@unsafe` on `toy_s08_unchecked` |
| L008 | `TOY-S-09` is named `toy_bad_name_9x`, not `toy_s09_...` |
| L009 | `toy_s07_renamed_comm` is `toy_s06_left_comm` with renamed parameters |
| L010 | `toy_s10_unknown_symbol` calls `U32.frobnicate` |
| L011 | `toy_f02_no_translation`: class L-FUNC with no translation and no reason |
| L012 | `toy_s11_no_priority`: `priority: null` |
| L013 | `toy_s05_conjunction` states two equalities in one law |
| L014 | `hashes: LAWS.bend` is all zeroes |
| L015 | `provenance.yaml` exists, but both digests are zeroes |

The package is not compiled and must not be: two of these defects only make
sense at the text layer, which is where the rules run.
