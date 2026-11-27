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

import json
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


class TestVerilatorDut(unittest.TestCase):
    """The real-DUT plumbing, everything that does not need the simulator."""

    def test_stimulus_is_one_hex_value_per_line(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "stim.hex"
            vp.write_stimulus(path, [0, 1, 15], 4)
            self.assertEqual(path.read_text(encoding="utf-8").split(), ["0", "1", "f"])
            vp.write_stimulus(path, [0, 16], 8)
            self.assertEqual(path.read_text(encoding="utf-8").split(), ["00", "10"])

    def test_trace_parser_ignores_blanks_and_comments(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "dut_trace.txt"
            path.write_text("0\n\n3\n# note\n15\n", encoding="utf-8")
            self.assertEqual(vp.parse_trace(path), [0, 3, 15])

    def test_shift_trace_keeps_length_and_order(self) -> None:
        self.assertEqual(vp.shift_trace([1, 2, 3], 1), [1, 1, 2])
        self.assertEqual(vp.shift_trace([1, 2, 3], 0), [1, 2, 3])
        self.assertEqual(vp.shift_trace([], 2), [])

    def test_the_command_can_name_its_container_so_a_hang_can_be_killed(self) -> None:
        command = vp.verilator_command(
            Path("/tmp/work"), 4, name="bendeda-dut-x"
        )
        self.assertEqual(command[command.index("--name") + 1], "bendeda-dut-x")

    def test_a_simulation_that_hangs_is_removed_and_reported(self) -> None:
        import subprocess

        fixture = ROOT / "experiments" / "fixtures" / "toy_counter"
        removed: list[list[str]] = []
        seen: list[list[str]] = []

        def runner(argv, **kwargs):
            seen.append(list(argv))
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

        with self.assertRaises(RuntimeError) as caught:
            vp.simulate_verilator(
                fixture / "dut.sv",
                fixture / "dut.json",
                {"incs": [1, 2], "stimulus": {"inc": [1, 2]}},
                timeout=5,
                runner=runner,
                remove=lambda argv, **kwargs: removed.append(list(argv)),
            )

        self.assertIn("did not finish within 5s", str(caught.exception))
        self.assertEqual(len(removed), 1, "the hung container must be removed exactly once")
        self.assertEqual(removed[0][:3], ["docker", "rm", "-f"])
        name = removed[0][3]
        self.assertIn("--name", seen[0])
        self.assertEqual(seen[0][seen[0].index("--name") + 1], name)

    def test_command_runs_the_pinned_image_and_the_testbench(self) -> None:
        command = vp.verilator_command(Path("/tmp/work"), 12, image="example/img:1", docker="docker")
        joined = " ".join(command)
        self.assertIn("example/img:1", command)
        self.assertIn("--binary", joined)
        self.assertIn("--top-module tb_dut", joined)
        self.assertIn("+cycles=12", joined)

    def test_a_recorded_trace_can_be_judged(self) -> None:
        model = steps([1, 2, 3, 4])  # model: 1, 3, 6, 7
        result = vp.compare(model, dut_trace=[1, 3, 3, 15])
        self.assertFalse(result.matches)
        self.assertEqual(result.detected_offset, 0)
        self.assertEqual(result.first_divergence, 2)  # third sample: 6 vs 3
        self.assertIn("value mismatch", result.explain())

    def test_injected_offset_applies_to_a_real_trace_too(self) -> None:
        model = steps([1, 2, 3, 4, 5, 6])
        trace = [step["out"] for step in model]
        result = vp.compare(model, dut_trace=trace, inject_offset=1)
        self.assertEqual(result.detected_offset, 1)

    def test_a_missing_docker_is_reported_as_unavailable(self) -> None:
        self.assertFalse(vp.image_available("any/image:1", docker="definitely-not-a-docker-xyz"))


class TestGeneratedTestbench(unittest.TestCase):
    """The manifest is the contract; the testbench is output."""

    def test_rendered_bench_connects_every_declared_port(self) -> None:
        bench = vp.render_testbench(ROOT / "experiments" / "fixtures" / "toy_counter" / "dut.json")
        for fragment in (
            "module tb_dut;",
            "toy_counter dut (",
            ".clk(clk)",
            ".rst(rst)",
            ".en(en)",
            ".inc(inc)",
            ".c(c)",
            'readmemh("stim.hex", stim)',
            'fopen("dut_trace.txt", "w")',
            '$fdisplay(fd, "%0d", c)',
        ):
            self.assertIn(fragment, bench)

    def test_stimulus_packs_inputs_in_manifest_order(self) -> None:
        spec = {
            "top": "dut",
            "clock": {"port": "clk"},
            "inputs": [
                {"port": "a", "width": 4, "stimulus": "incs"},
                {"port": "b", "width": 4, "stimulus": "const", "value": 3},
            ],
            "outputs": [{"port": "y", "width": 8}],
        }
        words, width = vp.build_stimulus(spec, {"incs": [1, 15]})
        self.assertEqual(width, 8)
        self.assertEqual(words, [0x31, 0x3F])

    def test_two_inputs_follow_their_own_sequences(self) -> None:
        spec = {
            "top": "dut",
            "clock": {"port": "clk"},
            "inputs": [
                {"port": "a", "width": 4, "stimulus": "plan", "key": "a"},
                {"port": "en", "width": 4, "stimulus": "plan", "key": "en"},
            ],
            "outputs": [{"port": "y", "width": 8}],
        }
        plan = {"incs": [1, 2], "stimulus": {"a": [1, 2], "en": [9, 0]}}
        words, width = vp.build_stimulus(spec, plan)
        self.assertEqual(width, 8)
        self.assertEqual(words, [0x91, 0x02])

    def test_a_missing_sequence_names_the_input(self) -> None:
        spec = {
            "top": "dut",
            "clock": {"port": "clk"},
            "inputs": [{"port": "en", "width": 1, "stimulus": "plan"}],
            "outputs": [{"port": "y", "width": 1}],
        }
        with self.assertRaises(ValueError) as caught:
            vp.build_stimulus(spec, {"incs": [1]})
        self.assertIn("stimulus.en", str(caught.exception))

    def test_a_short_sequence_is_rejected(self) -> None:
        spec = {
            "top": "dut",
            "clock": {"port": "clk"},
            "inputs": [{"port": "a", "width": 1, "stimulus": "plan"}],
            "outputs": [{"port": "y", "width": 1}],
        }
        with self.assertRaises(ValueError) as caught:
            vp.build_stimulus(spec, {"incs": [1, 2, 3], "stimulus": {"a": [1, 0]}})
        self.assertIn("2 values for 3 cycles", str(caught.exception))

    def test_the_default_plan_names_the_fixture_input(self) -> None:
        plan = vp.default_plan(6)
        self.assertEqual(plan["stimulus"]["inc"], plan["incs"])
        self.assertEqual(len(plan["incs"]), 6)

    def test_a_plan_without_count0_defaults_to_zero(self) -> None:
        plan = vp.load_plan({"incs": [1, 2]})
        self.assertEqual(plan["count0"], 0)
        self.assertEqual(plan["entries"], ["step", "run"])

    def test_multi_output_bench_samples_every_output(self) -> None:
        spec = {
            "top": "dut",
            "clock": {"port": "clk"},
            "inputs": [{"port": "a", "width": 1, "stimulus": "incs"}],
            "outputs": [{"port": "x", "width": 2}, {"port": "y", "width": 2}],
            "compare": "y",
        }
        bench = vp.render_testbench(spec)
        self.assertIn('$fdisplay(fd, "%0d %0d", x, y)', bench)
        self.assertEqual(vp.validate_spec(spec)["compare"], "y")

    def test_manifest_rejects_an_unknown_compare_port(self) -> None:
        spec = {
            "top": "dut",
            "clock": {"port": "clk"},
            "inputs": [],
            "outputs": [{"port": "y", "width": 1}],
            "compare": "nope",
        }
        with self.assertRaises(ValueError):
            vp.validate_spec(spec)

    def test_manifest_rejects_a_bad_identifier(self) -> None:
        spec = {
            "top": "dut",
            "clock": {"port": "clk"},
            "inputs": [{"port": "1bad", "width": 1}],
            "outputs": [{"port": "y", "width": 1}],
        }
        with self.assertRaises(ValueError):
            vp.validate_spec(spec)

    def test_manifest_requires_an_output(self) -> None:
        spec = {"top": "dut", "clock": {"port": "clk"}, "inputs": [], "outputs": []}
        with self.assertRaises(ValueError):
            vp.validate_spec(spec)

    def test_trace_table_parses_each_column(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "dut_trace.txt"
            path.write_text("0 3\n# note\n1 2\n", encoding="utf-8")
            self.assertEqual(vp.parse_trace_table(path, 2), [[0, 3], [1, 2]])


class TestRealDut(unittest.TestCase):
    """Compile the model, simulate the RTL, compare. Skipped without Docker."""

    def setUp(self) -> None:
        if shutil.which("docker") is None:
            raise unittest.SkipTest(
                "no docker: the Verilator DUT runs in the pinned image, and CI covers it"
            )
        if not vp.image_available():
            raise unittest.SkipTest(
                f"image {vp.DEFAULT_IMAGE} is not present; the oss-cad-image job builds it and runs this test"
            )
        bun, cli = vp.find_bend_toolchain()
        if bun is None or cli is None:
            raise unittest.SkipTest("no pinned Bend source (BENDEDA_BEND_CLI); CI supplies it")
        self.bun, self.cli = bun, cli

    def test_rtl_agrees_with_the_model(self) -> None:
        fixture = ROOT / "experiments" / "fixtures" / "toy_counter"
        with tempfile.TemporaryDirectory() as raw:
            module = Path(raw) / "model.mjs"
            compiled = vp.compile_model(fixture / "model.bend", module, Path(self.cli), self.bun)
            self.assertTrue(compiled.ok, msg=(compiled.stderr or compiled.stdout)[:1500])
            payload = vp.run_vectors(module, vp.default_plan(24))
        incs = [step["inc"] for step in payload["steps"]]
        trace = vp.simulate_verilator(
            fixture / "dut.sv",
            fixture / "dut.json",
            {"incs": incs, "stimulus": {"inc": list(incs)}},
        )
        comparison = vp.compare(payload["steps"], dut_trace=trace)
        self.assertTrue(comparison.matches, msg=comparison.explain())


class TestAlgebraicStimulus(unittest.TestCase):
    """A plan of operations, not increments: an ADT input is still driveable."""

    SPEC = {
        "top": "fifo",
        "clock": {"port": "clk"},
        "reset": {"port": "rst_n", "active_high": False, "cycles": 1},
        "inputs": [
            {"port": "push", "width": 1, "stimulus": "plan", "key": "push"},
            {"port": "din", "width": 8, "stimulus": "plan", "key": "din"},
        ],
        "outputs": [{"port": "dout", "width": 8}],
        "compare": "dout",
    }

    def test_an_ops_plan_is_accepted_with_its_length_as_the_cycle_count(self) -> None:
        plan = vp.validate_plan({"ops": [{"op": "Push", "din": 1}, {"op": "Pop"}]})
        self.assertEqual(len(plan["ops"]), 2)
        self.assertNotIn("incs", plan, "an ops plan has no increment list to invent")

    def test_an_operation_without_a_name_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            vp.validate_plan({"ops": [{"din": 1}]})
        self.assertIn("ops[0]", str(caught.exception))

    def test_stimulus_for_an_ops_plan_is_packed_in_port_order(self) -> None:
        plan = {
            "ops": [{"op": "Push", "din": 5}],
            "stimulus": {"push": [1], "din": [5]},
        }
        words, width = vp.build_stimulus(self.SPEC, plan)
        self.assertEqual(width, 9)
        self.assertEqual(words, [1 | (5 << 1)])

    def test_an_input_that_wants_incs_is_refused_on_an_ops_plan(self) -> None:
        spec = {**self.SPEC, "inputs": [
            {"port": "push", "width": 1, "stimulus": "incs"},
        ]}
        with self.assertRaises(ValueError) as caught:
            vp.build_stimulus(spec, {"ops": [{"op": "Push", "din": 1}]})
        self.assertIn("ops plan does not define", str(caught.exception))


class TestAlgebraicEndToEnd(unittest.TestCase):
    """Compile B1's model, run its plan through the driver, simulate the RTL."""

    def setUp(self) -> None:
        if shutil.which("docker") is None:
            raise unittest.SkipTest(
                "no docker: the Verilator DUT runs in the pinned image, and CI covers it"
            )
        if not vp.image_available():
            raise unittest.SkipTest(
                f"image {vp.DEFAULT_IMAGE} is not present; the oss-cad-image job builds it and runs this test"
            )
        bun, cli = vp.find_bend_toolchain()
        if bun is None or cli is None:
            raise unittest.SkipTest("no pinned Bend source (BENDEDA_BEND_CLI); CI supplies it")
        self.bun, self.cli = bun, cli

    def test_an_ops_plan_agrees_with_the_fifo(self) -> None:
        model = ROOT / "tasks" / "seq" / "B1_fifo" / "model.bend"
        submission = ROOT / "experiments" / "corpus" / "b1_fifo_rtl" / "submission"
        plan = json.loads((submission / "plan.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as raw:
            module = Path(raw) / "model.mjs"
            compiled = vp.compile_model(model, module, Path(self.cli), self.bun)
            self.assertTrue(compiled.ok, msg=(compiled.stderr or compiled.stdout)[:1500])
            payload = vp.run_vectors(module, plan)
        trace = vp.simulate_verilator(submission / "dut.sv", submission / "dut.json", plan)
        comparison = vp.compare(payload["steps"], dut_trace=trace)
        self.assertTrue(comparison.matches, msg=comparison.explain())


if __name__ == "__main__":
    unittest.main()
