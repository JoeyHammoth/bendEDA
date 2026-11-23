# SPDX-License-Identifier: Apache-2.0
"""Checker canary suite (issue #9).

A false accept here halts every Bend arm, so this package is deliberately
conservative: it fails on a control that was refused for the wrong reason as
well as on one that was accepted, and it reports exit code 3 rather than 0 when
the checker could not run.
"""

from bendeda.canary.controls import CONTROLS, Control, negatives, positives, select
from bendeda.canary.runner import (
    DEFAULT_BEND_IMAGE,
    Checker,
    Outcome,
    SuiteResult,
    build_checker,
    format_table,
    print_failures,
    run_control,
    run_suite,
    stage_of,
    write_report,
)

__all__ = [
    "CONTROLS",
    "DEFAULT_BEND_IMAGE",
    "Checker",
    "Control",
    "Outcome",
    "SuiteResult",
    "build_checker",
    "format_table",
    "negatives",
    "positives",
    "print_failures",
    "run_control",
    "run_suite",
    "select",
    "stage_of",
    "write_report",
]
