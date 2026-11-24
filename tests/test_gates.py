# SPDX-License-Identifier: Apache-2.0
"""The gates, with every external tool substituted (issue #15, `V`).

The real gates run Bun, Node, Verilator and SymbiYosys; those are exercised live in
docs/policy-proxy.md. These tests pin the decision logic: what counts as a fail, what
counts as a skip, and that a skip never becomes a pass.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bendeda.gates import GATES, run_gates, skipped, trace_gate, verdicts, formal_gate
from bendeda.plugins import GateResult


class Compile:
    def __init__(self, ok: bool = True, stderr: str = "") -> None:
        self.ok = ok
        self.output = Path("model.mjs") if ok else None
        self.stdout = ""
        self.stderr = stderr


def submissions(root: Path) -> None:
    (root / "model.bend").write_text("# model\n", encoding="utf-8")
    (root / "dut.sv").write_text("module dut; endmodule\n", encoding="utf-8")
    (root / "dut.json").write_text(
        json.dumps(
            {
                "top": "dut",
                "clock": {"port": "clk"},
                "inputs": [{"port": "inc", "width": 4}],
                "outputs": [{"port": "out"}],
                "compare": "out",
            }
        ),
        encoding="utf-8",
    )


def toolchain():
    return ("bun", Path("bend2/main.ts"))


class TestTraceGate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        submissions(self.root)

    def test_a_missing_artifact_is_a_failure_naming_it(self) -> None:
        (self.root / "dut.sv").unlink()
        result = trace_gate(self.root, {}, toolchain=toolchain)
        self.assertEqual(result.status, "fail")
        self.assertIn("dut.sv", result.reason)

    def test_without_a_compiler_the_gate_skips_rather_than_passing(self) -> None:
        result = trace_gate(self.root, {}, toolchain=lambda: (None, None))
        self.assertEqual(result.status, "skip")
        self.assertEqual(verdicts({"trace": result}), {})
        self.assertEqual(skipped({"trace": result}), ["trace"])

    def test_without_the_image_the_gate_skips(self) -> None:
        result = trace_gate(
            self.root, {}, toolchain=toolchain, available=lambda *_: False
        )
        self.assertEqual(result.status, "skip")
        self.assertIn("not present", result.reason)

    def test_agreement_passes(self) -> None:
        result = trace_gate(
            self.root,
            {},
            toolchain=toolchain,
            available=lambda *_: True,
            compile_fn=lambda *a, **k: Compile(),
            vectors=lambda *a, **k: {"steps": [{"out": 1}, {"out": 2}]},
            simulate=lambda *a, **k: [1, 2],
        )
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.detail["cycles"], 2)

    def test_disagreement_fails_with_the_first_cycle(self) -> None:
        result = trace_gate(
            self.root,
            {},
            toolchain=toolchain,
            available=lambda *_: True,
            compile_fn=lambda *a, **k: Compile(),
            vectors=lambda *a, **k: {"steps": [{"out": 1}, {"out": 2}]},
            simulate=lambda *a, **k: [1, 9],
        )
        self.assertEqual(result.status, "fail")
        self.assertIn("cycle 1", result.reason)

    def test_a_model_that_does_not_compile_fails_with_the_checker_output(self) -> None:
        result = trace_gate(
            self.root,
            {},
            toolchain=toolchain,
            available=lambda *_: True,
            compile_fn=lambda *a, **k: Compile(False, "type mismatch in step"),
        )
        self.assertEqual(result.status, "fail")
        self.assertIn("type mismatch", result.reason)

    def test_a_missing_driver_is_a_skip_not_a_failure(self) -> None:
        result = trace_gate(
            self.root,
            {},
            toolchain=toolchain,
            available=lambda *_: True,
            compile_fn=lambda *a, **k: Compile(),
            vectors=lambda *a, **k: (_ for _ in ()).throw(OSError("no node")),
        )
        self.assertEqual(result.status, "skip")


class TestFormalGate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "counter.sby").write_text("[tasks]\nprove\n", encoding="utf-8")
        (self.root / "counter.sv").write_text("module counter; endmodule\n", encoding="utf-8")

    def test_no_job_is_a_failure(self) -> None:
        (self.root / "counter.sby").unlink()
        result = formal_gate(self.root, {}, available=lambda *_: True)
        self.assertEqual(result.status, "fail")
        self.assertIn("no .sby", result.reason)

    def test_no_image_skips(self) -> None:
        result = formal_gate(self.root, {}, available=lambda *_: False)
        self.assertEqual(result.status, "skip")

    def test_a_pass_marker_passes(self) -> None:
        def run(argv):
            source = Path(str(argv[argv.index("--mount") + 1]).split("source=")[1].split(",")[0])
            (source / f"{argv[-3]}.out").mkdir(parents=True, exist_ok=True)
            (source / f"{argv[-3]}.out" / "PASS").write_text("", encoding="utf-8")
            return 0, ""

        result = formal_gate(self.root, {}, run=run, available=lambda *_: True)
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.detail["jobs"], ["counter.sby"])

    def test_a_nonzero_exit_fails(self) -> None:
        result = formal_gate(
            self.root, {}, run=lambda argv: (1, "ERROR: no solver"), available=lambda *_: True
        )
        self.assertEqual(result.status, "fail")
        self.assertIn("no solver", result.reason)

    def test_the_gate_does_not_write_into_the_artifacts(self) -> None:
        before = sorted(p.name for p in self.root.iterdir())

        formal_gate(self.root, {}, run=lambda argv: (0, ""), available=lambda *_: True)

        self.assertEqual(sorted(p.name for p in self.root.iterdir()), before)


class TestRegistry(unittest.TestCase):
    def test_the_registry_names_the_gates_that_execute(self) -> None:
        self.assertEqual(sorted(GATES), ["formal", "trace"])

    def test_an_unknown_gate_raises_rather_than_being_ignored(self) -> None:
        with self.assertRaises(KeyError):
            run_gates(".", ["no-such-gate"])

    def test_a_skip_is_absent_from_the_verdict_map(self) -> None:
        results = {
            "trace": GateResult("trace", "pass"),
            "formal": GateResult("formal", "skip", reason="no image"),
        }
        self.assertEqual(verdicts(results), {"trace": True})
        self.assertEqual(skipped(results), ["formal"])


if __name__ == "__main__":
    unittest.main()
