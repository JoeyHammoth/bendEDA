# SPDX-License-Identifier: Apache-2.0
"""Conformance rungs that can run without an EDA toolchain.

L1 (trace conformance) is here because it needs only the Bend compiler and Node.
L2 and L3 need simulation and formal tools and live behind `bendeda gate`.
"""

from bendeda.conformance.vector_path import (
    image_available,
    load_plan,
    CompileResult,
    Comparison,
    compare,
    compile_model,
    default_plan,
    find_bend_toolchain,
    run_vectors,
    saturating_dut,
)

__all__ = [
    "CompileResult",
    "Comparison",
    "compare",
    "compile_model",
    "default_plan",
    "find_bend_toolchain",
    "run_vectors",
    "saturating_dut",
]
