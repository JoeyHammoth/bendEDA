# SPDX-License-Identifier: Apache-2.0
"""Matrix expansion and one executed cell, with the sandbox and tools substituted."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bendeda.gates import GateResult
from bendeda.matrix import Cell, Task, execute_cell, expand, load
from bendeda.score import load as load_bundle


def matrix_file(root: Path, overrides: dict | None = None) -> Path:
    data = {
        "name": "smoke",
        "tasks": [{"name": "toy_counter", "artifacts": str(root)}],
        "arms": ["C0"],
        "seeds": [1],
        "command": ["python", "-m", "bendeda", "--version"],
        "visible_gates": ["trace"],
    }
    data.update(overrides or {})
    path = root / "matrix.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestLoadAndExpand(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_expansion_is_task_then_arm_then_seed(self) -> None:
        path = matrix_file(self.root, {"arms": ["C0", "C1"], "seeds": [1, 2]})
        cells = expand(load(path))
        self.assertEqual(
            [cell.label for cell in cells],
            ["C0-toy_counter-s1", "C0-toy_counter-s2", "C1-toy_counter-s1", "C1-toy_counter-s2"],
        )

    def test_a_matrix_with_no_arms_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            load(matrix_file(self.root, {"arms": []}))

    def test_a_task_without_artifacts_on_disk_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            load(matrix_file(self.root, {"tasks": [{"name": "missing", "artifacts": str(self.root / "nope")}]}))

    def test_a_bad_seed_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            load(matrix_file(self.root, {"seeds": [0]}))

    def test_the_command_must_be_a_list_of_strings(self) -> None:
        with self.assertRaises(ValueError):
            load(matrix_file(self.root, {"command": "python -m bendeda"}))


class TestExecuteCell(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        path = matrix_file(self.artifacts)
        self.matrix = load(path)
        self.cell = Cell(task=Task("toy_counter", self.artifacts), arm="C0", seed=1)
        self.calls: list[str] = []

    def deps(self, *, exec_code: int = 0, gates: dict | None = None, down_raises: bool = False) -> dict:
        bundle_events = {"path": None}

        def up(spec):
            self.calls.append("up")
            bundle_events["path"] = spec.events
            spec.events.parent.mkdir(parents=True, exist_ok=True)
            spec.events.write_text("", encoding="utf-8")

        def run(agent, command):
            self.calls.append(("exec", agent, tuple(command)))
            return exec_code, "ok" if exec_code == 0 else "boom"

        def submit(agent, resource):
            self.calls.append(("submit", resource))
            with bundle_events["path"].open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"seq": 1, "tool": "submit", "resource": resource, "action": "allow", "rule": "read-workspace"}) + "\n")
            return 0, "200"

        def down(spec):
            self.calls.append("down")
            if down_raises:
                raise RuntimeError("daemon gone")

        def gate_results(artifacts, names, image):
            self.calls.append(("gates", tuple(names)))
            return gates or {"trace": GateResult("trace", "pass")}

        from bendeda.score import report

        return {
            "up": up,
            "exec": run,
            "submit": submit,
            "down": down,
            "gates": gate_results,
            "score": lambda bundle, policy: report(load_bundle(bundle)),
        }

    def test_a_passing_cell_leaves_a_scored_bundle(self) -> None:
        record = execute_cell(self.matrix, self.cell, self.root / "runs", self.deps())

        bundle = Path(record["bundle"])
        self.assertTrue((bundle / "events.jsonl").is_file())
        self.assertTrue((bundle / "gates.json").is_file())
        self.assertTrue((bundle / "expected.json").is_file())
        self.assertTrue((bundle / "cell.json").is_file())
        self.assertEqual((record["S"], record["V"]), (1, 1))
        self.assertIsNone(record["O"], "the oracle is scored elsewhere, so O stays absent")
        self.assertFalse(record["complete"])
        self.assertIsNone(record["error"])

    def test_the_submission_is_recorded_through_the_agent(self) -> None:
        execute_cell(self.matrix, self.cell, self.root / "runs", self.deps())
        self.assertIn(("submit", "toy_counter/submission"), self.calls)

    def test_a_failed_command_scores_zero_and_still_tears_down(self) -> None:
        record = execute_cell(self.matrix, self.cell, self.root / "runs", self.deps(exec_code=7))

        self.assertIn("down", self.calls)
        self.assertNotIn(("submit", "toy_counter/submission"), self.calls)
        self.assertEqual((record["S"], record["V"], record["O"]), (0, 0, 0))
        self.assertIn("exited 7", record["error"])

    def test_a_refused_submission_is_recorded_and_scores_zero(self) -> None:
        deps = self.deps()
        deps["submit"] = lambda agent, resource: (1, "refused 403")

        record = execute_cell(self.matrix, self.cell, self.root / "runs", deps)

        self.assertIn("refused", record["error"])
        self.assertEqual(record["S"], 0)

    def test_teardown_runs_when_a_step_raises(self) -> None:
        deps = self.deps(down_raises=True)
        with self.assertRaises(RuntimeError):
            execute_cell(self.matrix, self.cell, self.root / "runs", deps)
        self.assertIn("down", self.calls)

    def test_a_skipped_gate_is_absent_from_gates_json(self) -> None:
        record = execute_cell(
            self.matrix,
            self.cell,
            self.root / "runs",
            self.deps(gates={"trace": GateResult("trace", "skip", reason="no image")}),
        )
        gates = json.loads((Path(record["bundle"]) / "gates.json").read_text(encoding="utf-8"))
        self.assertEqual(gates, {})
        self.assertEqual(record["skipped"], ["trace"])
        self.assertIsNone(record["V"], "a gate that never ran cannot be a pass")


if __name__ == "__main__":
    unittest.main()
