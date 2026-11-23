# SPDX-License-Identifier: Apache-2.0
"""Law authoring gates (issue #10).

`lint` judges a law set against rules L001-L015; `mutate` supplies the evidence
rule L006 needs by mutating the model and asking the checker which laws notice.
They are separate commands because they fail for different reasons: a law can
be well formed and still model-insensitive.
"""

from bendeda.laws.lint import Report, cmd_lint, discover, format_report, run
from bendeda.laws.manifest import (
    MANIFEST_NAME,
    LawEntry,
    Manifest,
    ManifestError,
)
from bendeda.laws.mutate import cmd_mutate, run_mutation
from bendeda.laws.rules import RULES, Finding, Package, check, load_package
from bendeda.laws.source import BendFile, Law, Param, parse

__all__ = [
    "MANIFEST_NAME",
    "RULES",
    "BendFile",
    "Finding",
    "Law",
    "LawEntry",
    "Manifest",
    "ManifestError",
    "Package",
    "Param",
    "Report",
    "check",
    "cmd_lint",
    "cmd_mutate",
    "discover",
    "format_report",
    "load_package",
    "parse",
    "run",
    "run_mutation",
]
