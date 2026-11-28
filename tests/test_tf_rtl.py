# SPDX-License-Identifier: Apache-2.0
"""The RTL side of TF (step 3 of `docs/research/2026-11-28-tf-run-design.md`).

The thing under test is the boundary to a simulator, so the assertions run in the
pinned Verilator image rather than against a stub: a stubbed bench would pass while
the generated testbench, the `FORMAL` instantiation or the message format was wrong,
and every one of those is what this step adds.

The corpus is the control. `as_shipped` must be clean, and the two entries the corpus
already names must fire the assertion it names: `m01_pop_keeps_count` fires
`p_pop_full_count`, `v06_lifo_shift` fires `p_pop_full_next_head`. A bench that
reports the first without the others is not observing anything.

They skip when the simulator image is absent and the skip says what was not measured.
The job that owns this path is `bend and EDA gates`; the Python test jobs have no
5 GB image and have nothing to say about it.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from bendeda import tf_rtl
from bendeda.conformance.vector_path import image_available
from bendeda.laws.manifest import Manifest

ROOT = Path(__file__).resolve().parents[1]
B1 = ROOT / "tasks" / "seq" / "B1_fifo"
CORPUS = ROOT / "experiments" / "corpus" / "b1_fifo_rtl"
PROPS = B1 / "props_locked.sv"


def fifo_trace(*ops: tuple[str, int | None]) -> dict[str, list[int]]:
    """A per-input trace from model operations, the shape a plan calls `stimulus`."""
    trace: dict[str, list[int]] = {"push": [], "pop": [], "din": []}
    for op, value in ops:
        trace["push"].append(1 if op in ("push", "pushpop") else 0)
        trace["pop"].append(1 if op in ("pop", "pushpop") else 0)
        trace["din"].append(int(value or 0))
    return trace


#: Push to half, push to full, pop from full (the cycle both variants get wrong),
#: then enough traffic after it that a bench reporting the first failure is not
#: merely reporting the last cycle.
TRACE = fifo_trace(
    ("push", 11),
    ("push", 22),
    ("pop", None),
    ("idle", None),
    ("push", 33),
    ("push", 44),
    ("pushpop", 55),
    ("pop", None),
)


def simulator_missing() -> str | None:
    if not image_available():
        return "the pinned simulator image is not present, so no assertion was observed"
    return None


class TestBenchSource(unittest.TestCase):
    """Generation, which needs no Docker."""

    def setUp(self) -> None:
        self.manifest = Manifest.load(B1 / "laws.manifest.yaml")
        self.declared = tf_rtl.declared_assertions(PROPS)

    def test_the_pack_declares_every_assertion_the_manifest_translates(self) -> None:
        self.assertEqual(len(self.declared), 19)
        self.assertIn("p_pop_full_count", self.declared)
        self.assertIn("p_pop_full_next_head", self.declared)
        # Both directions: a label the manifest claims but the pack does not carry
        # would be a translation that never reached the file.
        self.assertEqual(set(tf_rtl.law_by_assertion(self.manifest)), set(self.declared))

    def test_the_bench_drives_the_manifest_ports(self) -> None:
        spec = {
            "top": "b1_fifo",
            "clock": {"port": "clk", "period_ns": 10},
            "reset": {"port": "rst_n", "active_high": False, "cycles": 1},
            "inputs": [
                {"port": "push", "width": 1, "stimulus": "plan", "key": "push"},
                {"port": "pop", "width": 1, "stimulus": "plan", "key": "pop"},
                {"port": "din", "width": 32, "stimulus": "plan", "key": "din"},
            ],
            "outputs": [
                {"port": "dout", "width": 32},
                {"port": "full", "width": 1},
                {"port": "empty", "width": 1},
            ],
            "compare": "dout",
        }
        bench = tf_rtl.render_bench(spec, traces=2, cycles=8)
        self.assertIn("reg rst_n = 1'b0;", bench)  # active low starts asserted
        self.assertIn("rst_n = 1'b1;", bench)      # and is deasserted before operations
        self.assertIn("push = row[0 +: 1];", bench)
        self.assertIn("din = row[2 +: 32];", bench)
        self.assertIn("dut (", bench)

    def test_a_ragged_trace_is_refused(self) -> None:
        spec = {
            "top": "b1_fifo",
            "clock": {"port": "clk", "period_ns": 10},
            "inputs": [
                {"port": "push", "width": 1, "stimulus": "plan", "key": "push"},
                {"port": "din", "width": 32, "stimulus": "plan", "key": "din"},
            ],
            "outputs": [{"port": "dout", "width": 32}],
        }
        with self.assertRaises(ValueError):
            tf_rtl.run_assertions(
                B1 / "props_locked.sv", PROPS, spec,
                [{"push": [1, 0], "din": [7]}],
            )


class TestCorpusAssertions(unittest.TestCase):
    """The measured control: clean on the reference, named failure on the variants."""

    def setUp(self) -> None:
        reason = simulator_missing()
        if reason:
            self.skipTest(reason)
        self.manifest = Manifest.load(B1 / "laws.manifest.yaml")

    def _report(self, dut: Path):
        return tf_rtl.run_assertions(
            dut, PROPS, json.loads((CORPUS / "submission" / "dut.json").read_text(encoding="utf-8")),
            [TRACE],
        )

    def test_the_reference_is_clean_and_the_variants_fire_the_named_assertion(self) -> None:
        reference = self._report(CORPUS / "submission" / "dut.sv")
        self.assertTrue(reference.verdicts[0].clean, reference.as_json())
        self.assertEqual(reference.image_id and reference.image_id.startswith("sha256:"), True)

        cases = {
            "m01_pop_keeps_count": ("p_pop_full_count", "FIFO-F-06", 2),
            "v06_lifo_shift": ("p_pop_full_next_head", "FIFO-F-07", 2),
        }
        by_assertion = tf_rtl.law_by_assertion(self.manifest)
        for entry, (label, law, cycle) in cases.items():
            with self.subTest(entry=entry):
                report = self._report(CORPUS / "mutant" / entry / "dut.sv"
                                      if (CORPUS / "mutant" / entry).is_dir()
                                      else CORPUS / "seeded" / entry / "dut.sv")
                failures = report.failures
                self.assertEqual(len(failures), 1, report.as_json())
                failure = failures[0].failure
                self.assertEqual(failure.assertion, label)
                # The pack judges a transition one edge after it happens: the trace
                # cycle is the simulator iteration minus one, and both are kept.
                self.assertEqual(failure.observed_at, cycle + 1)
                self.assertEqual(failure.cycle, cycle)
                self.assertEqual(by_assertion[failure.assertion], law)


if __name__ == "__main__":
    unittest.main()
