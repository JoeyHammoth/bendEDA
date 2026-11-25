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

from bendeda.gates import (
    GATES,
    calibrate,
    formal_gate,
    load_corpus,
    run_gates,
    skipped,
    stage,
    trace_gate,
    verdicts,
)
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


def make_corpus(root: Path, entries: list[tuple[str, str, str]]) -> None:
    """A base submission plus one-file variants, the shape `load_corpus` expects."""
    base = root / "base"
    base.mkdir()
    (base / "model.bend").write_text("# model\n", encoding="utf-8")
    (base / "dut.sv").write_text("// base\n", encoding="utf-8")
    (base / "dut.json").write_text(
        json.dumps(
            {
                "top": "dut",
                "clock": {"port": "clk"},
                "inputs": [],
                "outputs": [{"port": "y"}],
                "compare": "y",
            }
        ),
        encoding="utf-8",
    )
    manifest: dict = {"task": "toy", "base": "base", "gates": ["trace"], "entries": []}
    for identifier, kind, text in entries:
        directory = root / kind / identifier
        directory.mkdir(parents=True)
        (directory / "dut.sv").write_text(text, encoding="utf-8")
        manifest["entries"].append(
            {"id": identifier, "kind": kind, "artifacts": f"{kind}/{identifier}"}
        )
    (root / "corpus.json").write_text(json.dumps(manifest), encoding="utf-8")


def fake_run(seen: list[list[str]] | None = None):
    """A gate runner that answers from the staged RTL, and records what it saw."""

    def run(artifacts, names, cfg):
        if seen is not None:
            seen.append(sorted(path.name for path in Path(artifacts).iterdir()))
        text = (Path(artifacts) / "dut.sv").read_text(encoding="utf-8")
        status = "fail" if "REJECT" in text else "skip" if "SKIP" in text else "pass"
        return {
            name: GateResult(name, status, reason=f"{name} says {status}") for name in names
        }

    return run


GOOD = ("correct", ("a", "b", "c"))
BUGS = (
    ("mutant", ("m1",)),
    ("seeded", ("s1",)),
)


def standard(root: Path, **overrides: str) -> None:
    """Three correct implementations, one mutant and one seeded bug."""
    entries: list[tuple[str, str, str]] = []
    for kind, ids in (GOOD, *BUGS):
        for identifier in ids:
            text = overrides.get(identifier, "// REJECT\n" if kind != "correct" else "// ok\n")
            entries.append((identifier, kind, text))
    make_corpus(root, entries)


class TestCalibration(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_a_clean_corpus_calibrates(self) -> None:
        standard(self.root)
        report = calibrate(load_corpus(self.root), run=fake_run())

        self.assertEqual(report.gs(), 1.0)
        self.assertEqual(report.gsp(), 1.0)
        self.assertEqual(report.exit_code(), 0)
        self.assertEqual(report.counts("correct"), {"decided": 3, "total": 3})
        self.assertTrue(report.as_json()["ok"])

    def test_a_bug_no_gate_caught_is_a_failure_and_is_named(self) -> None:
        standard(self.root, m1="// passes\n")
        report = calibrate(load_corpus(self.root), run=fake_run())

        self.assertLess(report.gs(), 1.0)
        self.assertEqual([entry.id for entry in report.survivors()], ["m1"])
        self.assertEqual(report.exit_code(), 1)
        self.assertEqual(report.as_json()["survivors"], ["m1"])

    def test_sensitivity_is_reported_apart_for_mutants_and_seeded_bugs(self) -> None:
        standard(self.root, m1="// passes\n")
        report = calibrate(load_corpus(self.root), run=fake_run())

        self.assertEqual(report.gs("mutant"), 0.0)
        self.assertEqual(report.gs("seeded"), 1.0)
        self.assertEqual(report.as_json()["gs"]["mutant"], 0.0)

    def test_a_rejected_correct_implementation_fails_specificity(self) -> None:
        standard(self.root, c="// REJECT\n")
        report = calibrate(load_corpus(self.root), run=fake_run())

        self.assertLess(report.gsp(), 1.0)
        self.assertEqual([entry.id for entry in report.false_rejects()], ["c"])
        self.assertEqual(report.exit_code(), 1, "an over-fitted gate is a failure even at GS 1")

    def test_a_skipped_gate_leaves_the_entry_undecidable_and_uncalibrated(self) -> None:
        standard(self.root, s1="// SKIP\n")
        report = calibrate(load_corpus(self.root), run=fake_run())

        self.assertEqual([entry.id for entry in report.undecidable()], ["s1"])
        self.assertEqual(report.gs("seeded"), None, "nothing decidable of that kind")
        self.assertEqual(report.counts("seeded"), {"decided": 0, "total": 1})
        self.assertEqual(report.exit_code(), 3)
        self.assertEqual(report.as_json()["undecidable"], ["s1"])

    def test_fewer_than_three_correct_implementations_is_not_calibrated(self) -> None:
        make_corpus(
            self.root,
            [
                ("a", "correct", "// ok\n"),
                ("m1", "mutant", "// REJECT\n"),
                ("s1", "seeded", "// REJECT\n"),
            ],
        )
        report = calibrate(load_corpus(self.root), run=fake_run())

        self.assertEqual(report.exit_code(), 3)
        self.assertFalse(report.as_json()["ok"])

    def test_an_entry_overrides_the_base_and_the_base_is_untouched(self) -> None:
        standard(self.root)
        seen: list[list[str]] = []
        corpus = load_corpus(self.root)
        calibrate(corpus, run=fake_run(seen))

        self.assertEqual(seen[0], ["dut.json", "dut.sv", "model.bend"])
        self.assertEqual(
            sorted(path.name for path in corpus.base.iterdir()),
            ["dut.json", "dut.sv", "model.bend"],
        )
        staged = self.root / "staged"
        staged.mkdir()
        stage(corpus, corpus.entries[0], staged)
        self.assertEqual(
            (staged / "dut.sv").read_text(encoding="utf-8"), "// ok\n",
            "the entry's file wins over the base's",
        )

    def test_a_manifest_without_a_correct_entry_is_refused(self) -> None:
        make_corpus(self.root, [("m1", "mutant", "// REJECT\n")])
        with self.assertRaises(ValueError) as caught:
            load_corpus(self.root)
        self.assertIn("correct", str(caught.exception))

    def test_a_manifest_naming_a_gate_that_does_not_exist_is_refused(self) -> None:
        standard(self.root)
        manifest = json.loads((self.root / "corpus.json").read_text(encoding="utf-8"))
        manifest["gates"] = ["lint"]
        (self.root / "corpus.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError) as caught:
            load_corpus(self.root)
        self.assertIn("unknown gate", str(caught.exception))

    def test_a_duplicate_id_is_refused(self) -> None:
        standard(self.root)
        manifest = json.loads((self.root / "corpus.json").read_text(encoding="utf-8"))
        manifest["entries"].append(dict(manifest["entries"][0]))
        (self.root / "corpus.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError) as caught:
            load_corpus(self.root)
        self.assertIn("twice", str(caught.exception))

    def test_a_directory_without_a_manifest_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            load_corpus(self.root)
        self.assertIn("corpus.json", str(caught.exception))


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
