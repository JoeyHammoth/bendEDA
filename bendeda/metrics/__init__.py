# SPDX-License-Identifier: Apache-2.0
"""Metrics defined in §10 of the design document, with known-answer tests in
`tests/test_metrics.py`. Nothing here accepts an LLM judgement as an input."""

from bendeda.metrics.core import (
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

__all__ = [
    "Cells",
    "cells_from_runs",
    "cost_per_verified_success",
    "escape_rate",
    "false_assurance_rate",
    "gate_false_reject_rate",
    "gate_recall",
    "gate_sensitivity",
    "gate_specificity",
    "hidden_functional_pass",
    "law_coverage",
    "matthews_corrcoef",
    "mutation_kill_ratio",
    "net_verified_benefit",
    "pass_at_k",
    "spec_deficit",
    "translation_fidelity",
    "vacuity_rate",
    "verified_yield",
]
