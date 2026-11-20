# SPDX-License-Identifier: Apache-2.0
"""The L1 vector path (issue #7).

Two layers, deliberately separate:

* the comparator is unit-tested with hand-built vectors, so its behaviour is
  pinned even on a machine with no Bend compiler;
* the end-to-end compile → execute → compare test skips with a reason when the
  toolchain is absent. A skip that says why is honest; a pass without running
  would be the exact defect the programme studies.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from bendeda.conformance import vector_path as vp

ROOT = Path(__file__).resolve().parent.parent


def steps(incs: list[int]) -> list[dict]:
    count = 0
    out = []
    for inc in incs:
        count = vp.saturating_dut(count, inc)
        out.append({"inc": inc, "out": count})
    return out


class TestComparator(unittest.TestCase):
    def test_agreement_is_a_pass(self) -> None:
        result = vp.compare(steps([1, 2, 3]))
        self.assertTrue(result.matches)
        self.assertEqual(result.detected_offset, 0)
        self.assertEqual(result.total, 3)

    def test_wrong_value_is_not_an_offset(self) -> None:
        model = steps([1, 2, 3])
        model[1]["out"] = 99
        result = vp.compare(model)
        self.assertFalse(result.matches)
        self.assertEqual(result.detected_offset, 0)
        self.assertEqual(result.first_divergence, 1)
        self.assertIn("value mismatch", result.explain())

    def test_injected_one_cycle_offset_is_detected_as_an_offset(self) -> None:
        model = steps([1, 2, 3, 4, 5, 6])
        result = vp.compare(model, inject_offset=1)
        self.assertFalse(result.matches)
        self.assertEqual(result.detected_offset, 1)
        self.assertIn("offset detected", result.explain())

    def test_saturation_is_part_of_the_fixture_contract(self) -> None:
        self.assertEqual(vp.saturating_dut(14, 5), 15)
        self.assertEqual(vp.saturating_dut(15, 0), 15)

    def test_empty_comparison_is_not_a_pass(self) -> None:
        result = vp.compare([])
        self.assertFalse(result.matches)
        self.assertEqual(result.explain(), "no cycles compared")


class TestEndToEnd(unittest.TestCase):
    """Compile the fixture, execute it, compare it."""

    def setUp(self) -> None:
        bun, cli = vp.find_bend_toolchain()
        if bun is None or shutil.which(bun) is None:
            raise unittest.SkipTest("no bun on PATH (BENDEDA_BUN); the L1 driver needs Node plus bun")
        if cli is None:
            raise unittest.SkipTest(
                "no pinned Bend source (BENDEDA_BEND_CLI); fetch v2.0.40 bend2/*.ts or use the bend image"
            )
        self.bun = bun
        self.cli = cli
        self.tmp = tempfile.TemporaryDirectory()
        self.module = Path(self.tmp.name) / "model.mjs"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_compile_and_trace(self) -> None:
        model = ROOT / "experiments" / "fixtures" / "toy_counter" / "model.bend"
        compiled = vp.compile_model(model, self.module, Path(self.cli), self.bun)
        self.assertTrue(compiled.ok, msg=(compiled.stderr or compiled.stdout)[:1500])

        payload = vp.run_vectors(self.module, vp.default_plan(16))
        self.assertIn("step", payload["exports"])
        self.assertEqual(payload["limb"], 15)
        self.assertEqual(len(payload["steps"]), 16)

        comparison = vp.compare(payload["steps"], count0=0)
        self.assertTrue(comparison.matches, msg=comparison.explain())

        # The `run` fold and the cycle walk must agree, or the driver is lying.
        self.assertEqual(payload["run"], payload["steps"][-1]["out"])

    def test_injected_offset_breaks_the_trace_gate(self) -> None:
        model = ROOT / "experiments" / "fixtures" / "toy_counter" / "model.bend"
        compiled = vp.compile_model(model, self.module, Path(self.cli), self.bun)
        self.assertTrue(compiled.ok, msg=(compiled.stderr or compiled.stdout)[:1500])
        payload = vp.run_vectors(self.module, vp.default_plan(12))
        comparison = vp.compare(payload["steps"], inject_offset=1)
        self.assertFalse(comparison.matches)
        self.assertEqual(comparison.detected_offset, 1)


if __name__ == "__main__":
    unittest.main()
