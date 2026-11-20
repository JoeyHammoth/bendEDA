# SPDX-License-Identifier: Apache-2.0
"""bendeda — harness for evaluating Bend 2 laws and proof gates in agentic EDA.

The package is deliberately dependency-free at import time: the CLI, the metric
definitions and the schema validation must run on a bare Python install so that
CI and a reader on a clean machine can reproduce a result without a toolchain.
"""

__version__ = "0.0.1"
__all__ = ["__version__"]
