# SPDX-License-Identifier: Apache-2.0
"""Known-answer tests for the §10 metric definitions.

Each case is hand-computed from the definition in the design document so a
regression in the code is distinguishable from a disagreement about the maths.
"""

from __future__ import annotations

import unittest

from bendeda.metrics import (
    Cells,
    cells_from_runs,
    cost_per_verified_success,
    escape_rate,
    false_assurance_rate,
    gate_false_reject_rate,
    gate_recall,
    gate_sensitivity,
    gate_specificity,
    hidden_functional_pass,
    law_coverage,
    matthews_corrcoef,
    mutation_kill_ratio,
    net_verified_benefit,
    pass_at_k,
    spec_deficit,
    translation_fidelity,
    vacuity_rate,
    verified_yield,
)


class TestCells(unittest.TestCase):
    def test_counts_from_runs(self) -> None:
        runs = [(True, True), (True, False), (True, False), (False, True), (False, False)]
        cells = cells_from_runs(runs)
        self.assertEqual((cells.tp, cells.fp, cells.fn, cells.tn), (1, 2, 1, 1))
        self.assertEqual(cells.total, 5)
        self.assertEqual(cells.visible, 3)

    def test_negative_cell_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Cells(tp=-1)


class TestPrimaryMetrics(unittest.TestCase):
    def setUp(self) -> None:
        # 10 runs: 4 visibly pass, of which 1 is actually correct.
        self.cells = Cells(tp=1, fp=3, fn=2, tn=4)

    def test_hfp(self) -> None:
        # (TP + FN) / N = 3/10
        self.assertAlmostEqual(hidden_functional_pass(self.cells), 0.3)

    def test_far(self) -> None:
        # FP / N = 3/10, unconditional by design
        self.assertAlmostEqual(false_assurance_rate(self.cells), 0.3)

    def test_er(self) -> None:
        # FP / (TP + FP) = 3/4
        self.assertAlmostEqual(escape_rate(self.cells), 0.75)

    def test_vy_and_gr(self) -> None:
        self.assertAlmostEqual(verified_yield(self.cells), 0.1)
        self.assertAlmostEqual(gate_recall(self.cells), 1 / 3)
        self.assertAlmostEqual(gate_false_reject_rate(self.cells), 2 / 3)

    def test_mcc(self) -> None:
        expected = (1 * 4 - 3 * 2) / ((4 * 3 * 7 * 6) ** 0.5)
        self.assertAlmostEqual(matthews_corrcoef(self.cells), expected)

    def test_nvb_sweep(self) -> None:
        self.assertAlmostEqual(net_verified_benefit(self.cells, 1), (1 - 3) / 10)
        self.assertAlmostEqual(net_verified_benefit(self.cells, 5), (1 - 15) / 10)

    def test_cpvs(self) -> None:
        self.assertAlmostEqual(cost_per_verified_success(1000, self.cells), 1000.0)


class TestUndefinedIsNotZero(unittest.TestCase):
    """The most consequential bug class in this module is silently returning 0
    for a quantity that is undefined."""

    def test_empty_cells(self) -> None:
        empty = Cells()
        self.assertIsNone(hidden_functional_pass(empty))
        self.assertIsNone(false_assurance_rate(empty))
        self.assertIsNone(net_verified_benefit(empty, 1))

    def test_escape_rate_with_no_visible_pass(self) -> None:
        self.assertIsNone(escape_rate(Cells(tp=0, fp=0, fn=3, tn=1)))

    def test_cpvs_with_no_verified_success(self) -> None:
        self.assertIsNone(cost_per_verified_success(1000, Cells(tp=0, fp=2, fn=0, tn=1)))

    def test_mcc_with_empty_marginal(self) -> None:
        # Everything fails both gates: the coefficient is undefined, not 0.
        self.assertIsNone(matthews_corrcoef(Cells(tp=0, fp=0, fn=0, tn=5)))


class TestPassAtK(unittest.TestCase):
    def test_known_values(self) -> None:
        # n=10, c=2, k=1 -> 0.2 ; k=5 -> 1 - C(8,5)/C(10,5) = 1 - 56/252
        self.assertAlmostEqual(pass_at_k(10, 2, 1), 0.2)
        self.assertAlmostEqual(pass_at_k(10, 2, 5), 1 - 56 / 252)

    def test_boundaries(self) -> None:
        self.assertAlmostEqual(pass_at_k(5, 5, 3), 1.0)
        self.assertAlmostEqual(pass_at_k(5, 0, 3), 0.0)
        self.assertIsNone(pass_at_k(2, 1, 3))  # k > n
        self.assertIsNone(pass_at_k(0, 0, 1))


class TestGateAndSpecMetrics(unittest.TestCase):
    def test_sensitivity_and_specificity(self) -> None:
        self.assertAlmostEqual(gate_sensitivity(19, 20), 0.95)
        self.assertAlmostEqual(gate_specificity(3, 3), 1.0)
        self.assertIsNone(gate_sensitivity(0, 0))
        self.assertIsNone(gate_specificity(0, 0))

    def test_mkr_and_spec_deficit(self) -> None:
        self.assertAlmostEqual(mutation_kill_ratio(9, 10), 0.9)
        self.assertAlmostEqual(spec_deficit(0.97, 0.62), 0.35)
        self.assertIsNone(spec_deficit(None, 0.62))

    def test_coverage_vacuity_fidelity(self) -> None:
        self.assertAlmostEqual(law_coverage(9, 12), 0.75)
        self.assertAlmostEqual(vacuity_rate(1, 20), 0.05)
        self.assertAlmostEqual(translation_fidelity(999, 1000), 0.999)

    def test_parity_constraint_is_expressible(self) -> None:
        # |LC(C2) - LC(C3)| <= 0.05 is the admission rule from §5.2.
        # 18/20 and 19/20 differ by exactly the 5 percentage-point margin.
        c2, c3 = law_coverage(18, 20), law_coverage(19, 20)
        self.assertLessEqual(abs(c2 - c3), 0.05 + 1e-12)
        c3_weak = law_coverage(15, 20)
        self.assertGreater(abs(c2 - c3_weak), 0.05)


if __name__ == "__main__":
    unittest.main()
