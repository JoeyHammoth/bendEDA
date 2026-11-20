# SPDX-License-Identifier: Apache-2.0
"""Metric definitions from §10 of the design document.

Two rules govern this module:

1. A metric is a pure function of counts or of a list of run outcomes. If a
   quantity cannot be computed deterministically from logs and artifacts, it is
   not an endpoint and does not live here.
2. Undefined is a value, not an exception and never a zero. `EscapeRate` returns
   `None` when no run passed the visible gates; reporting ``0.0`` there would
   read as "no escapes" when the truth is "nothing to escape from".
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Cells:
    """Confusion cells over runs. ``V`` is the visible-gate verdict, ``O`` the oracle verdict."""

    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def visible(self) -> int:
        """Runs that looked verified (n_V)."""
        return self.tp + self.fp

    @property
    def oracle_pass(self) -> int:
        return self.tp + self.fn

    def __post_init__(self) -> None:
        if min(self.tp, self.fp, self.fn, self.tn) < 0:
            raise ValueError("confusion cells must be non-negative")


def cells_from_runs(outcomes: list[tuple[bool, bool]]) -> Cells:
    """Build cells from ``(visible, oracle)`` pairs."""
    tp = sum(1 for v, o in outcomes if v and o)
    fp = sum(1 for v, o in outcomes if v and not o)
    fn = sum(1 for v, o in outcomes if not v and o)
    tn = sum(1 for v, o in outcomes if not v and not o)
    return Cells(tp, fp, fn, tn)


def hidden_functional_pass(cells: Cells) -> float | None:
    """HFP: unconditional correctness yield, (1/N) * sum O_r."""
    return cells.oracle_pass / cells.total if cells.total else None


def false_assurance_rate(cells: Cells) -> float | None:
    """FAR = FP / N. The confirmatory endpoint: unconditional, so immune to
    selection into V=1."""
    return cells.fp / cells.total if cells.total else None


def escape_rate(cells: Cells) -> float | None:
    """ER = FP / (TP + FP). Conditional on a post-randomisation variable, so it is
    always reported next to FAR and never alone."""
    return cells.fp / cells.visible if cells.visible else None


def verified_yield(cells: Cells) -> float | None:
    return cells.tp / cells.total if cells.total else None


def gate_recall(cells: Cells) -> float | None:
    """GR = TP / (TP + FN): how often correct designs pass the visible gates."""
    return cells.tp / cells.oracle_pass if cells.oracle_pass else None


def gate_false_reject_rate(cells: Cells) -> float | None:
    """1 - GR, i.e. correct designs rejected by the gates (over-restriction)."""
    gr = gate_recall(cells)
    return None if gr is None else 1.0 - gr


def matthews_corrcoef(cells: Cells) -> float | None:
    """MCC: single-number agreement between gates and truth.

    Returns ``None`` when any marginal is empty, because the coefficient is then
    undefined rather than zero.
    """
    denominator = math.sqrt(
        (cells.tp + cells.fp) * (cells.tp + cells.fn) * (cells.tn + cells.fp) * (cells.tn + cells.fn)
    )
    if denominator == 0:
        return None
    return (cells.tp * cells.tn - cells.fp * cells.fn) / denominator


def pass_at_k(n: int, c: int, k: int) -> float | None:
    """Unbiased pass@k estimator (Chen et al.): 1 - C(n-c, k) / C(n, k).

    Returns ``None`` when ``k > n``: the estimator needs at least k samples.
    """
    if n <= 0 or k <= 0:
        return None
    if k > n:
        return None
    if c <= 0:
        return 0.0
    if n - c < k:
        return 1.0
    return 1.0 - (math.comb(n - c, k) / math.comb(n, k))


def net_verified_benefit(cells: Cells, lam: float) -> float | None:
    """NVB = (TP - lambda * FP) / N. A false assurance is worth ``-lambda`` verified
    successes, so the sweep over lambda is a utility sensitivity, not a new metric."""
    return (cells.tp - lam * cells.fp) / cells.total if cells.total else None


def cost_per_verified_success(total_cost: float, cells: Cells) -> float | None:
    """CPVS: cost of one trustworthy output. Undefined with no verified success —
    which is a finding, not a division error."""
    return total_cost / cells.tp if cells.tp else None


def gate_sensitivity(rejected: int, corpus: int) -> float | None:
    """GS = rejected / |B_t| over the bug corpus."""
    return rejected / corpus if corpus else None


def gate_specificity(accepted: int, correct: int) -> float | None:
    """GSp = accepted correct / correct. Needs >= 3 structurally different correct
    implementations per task to mean anything."""
    return accepted / correct if correct else None


def mutation_kill_ratio(killed: int, relevant: int) -> float | None:
    """MKR over mutants whose output change is confirmed by equivalence checking."""
    return killed / relevant if relevant else None


def spec_deficit(oracle_mkr: float | None, visible_mkr: float | None) -> float | None:
    if oracle_mkr is None or visible_mkr is None:
        return None
    return oracle_mkr - visible_mkr


def law_coverage(covered: int, requirements: int) -> float | None:
    """LC over the expert requirement checklist."""
    return covered / requirements if requirements else None


def vacuity_rate(unreachable: int, properties: int) -> float | None:
    return unreachable / properties if properties else None


def translation_fidelity(agreements: int, samples: int) -> float | None:
    return agreements / samples if samples else None


def cluster_bootstrap_seed_default() -> int:
    """The pre-registered default resample seed. Fixed so a re-run of the analysis
    reproduces the intervals rather than merely resembling them."""
    return 20261121
