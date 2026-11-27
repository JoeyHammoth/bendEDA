# SPDX-License-Identifier: Apache-2.0
"""The gates, with every external tool substituted (issue #15, `V`).

The real gates run Bun, Node, Verilator and SymbiYosys; those are exercised live in
docs/policy-proxy.md. These tests pin the decision logic: what counts as a fail, what
counts as a skip, and that a skip never becomes a pass.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from bendeda.conformance.vector_path import simulate_verilator
from bendeda.gates import (
    GATES,
    calibrate,
    formal_gate,
    lint_gate,
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
                # One input, because `validate_spec` refuses a design with nothing to
                # drive and the trace gate would fail before reaching a simulator.
                "inputs": [{"port": "inc", "width": 4}],
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


TASK = Path(__file__).resolve().parents[1] / "tasks" / "seq" / "B1_fifo"


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

    def test_a_corpus_can_stage_a_task_package_and_a_submission(self) -> None:
        standard(self.root)
        submission = self.root / "submission"
        submission.mkdir()
        (submission / "submission.txt").write_text("submitted\n", encoding="utf-8")
        (submission / "model.bend").write_text("// submission model\n", encoding="utf-8")
        manifest = json.loads((self.root / "corpus.json").read_text(encoding="utf-8"))
        manifest["bases"] = [manifest.pop("base"), "submission"]
        (self.root / "corpus.json").write_text(json.dumps(manifest), encoding="utf-8")

        corpus = load_corpus(self.root)
        self.assertEqual(len(corpus.bases), 2)
        staged = self.root / "staged-two"
        staged.mkdir()
        stage(corpus, corpus.entries[0], staged)

        self.assertTrue((staged / "dut.json").is_file(), "the task base is staged")
        self.assertTrue((staged / "submission.txt").is_file(), "the submission is staged")
        self.assertEqual(
            (staged / "model.bend").read_text(encoding="utf-8"),
            "// submission model\n",
            "a later base wins over an earlier one",
        )
        self.assertEqual(
            (staged / "dut.sv").read_text(encoding="utf-8"),
            "// ok\n",
            "the entry wins over every base",
        )

    def test_a_manifest_without_a_correct_entry_is_refused(self) -> None:
        make_corpus(self.root, [("m1", "mutant", "// REJECT\n")])
        with self.assertRaises(ValueError) as caught:
            load_corpus(self.root)
        self.assertIn("correct", str(caught.exception))

    def test_a_manifest_naming_a_gate_that_does_not_exist_is_refused(self) -> None:
        standard(self.root)
        manifest = json.loads((self.root / "corpus.json").read_text(encoding="utf-8"))
        manifest["gates"] = ["conformance"]
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


def gated_run():
    """A runner whose verdict comes from the file: `REJECT:<gate>` fails that gate."""

    def run(artifacts, names, cfg):
        text = (Path(artifacts) / "dut.sv").read_text(encoding="utf-8")
        results = {}
        for name in names:
            status = "fail" if f"REJECT:{name}" in text else "pass"
            results[name] = GateResult(name, status, reason=f"{name} says {status}")
        return results

    return run


def with_gates(root: Path, names: list[str]) -> None:
    path = root / "corpus.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["gates"] = names
    path.write_text(json.dumps(manifest), encoding="utf-8")


class TestContribution(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_a_sole_catcher_and_a_shared_catcher_are_counted_apart(self) -> None:
        standard(self.root, m1="// REJECT:trace\n", s1="// REJECT:trace\nREJECT:lint\n")
        with_gates(self.root, ["trace", "lint"])
        report = calibrate(load_corpus(self.root), run=gated_run())

        self.assertEqual(
            report.contribution()["trace"],
            {"catch": 2, "sole_catch": 1, "false_reject": 0},
            "trace caught both bugs, and one of them alone",
        )
        self.assertEqual(
            report.contribution()["lint"],
            {"catch": 1, "sole_catch": 0, "false_reject": 0},
            "lint caught the bug trace also caught, and nothing alone",
        )
        self.assertEqual(report.exit_code(), 0)

    def test_a_gate_that_catches_nothing_is_reported_as_inert(self) -> None:
        standard(self.root, m1="// REJECT:trace\n", s1="// REJECT:trace\n")
        with_gates(self.root, ["trace", "lint"])
        report = calibrate(load_corpus(self.root), run=gated_run())

        self.assertEqual(report.inert(), ["lint"])
        self.assertEqual(report.as_json()["inert"], ["lint"])
        self.assertEqual(report.as_json()["contribution"]["lint"]["catch"], 0)
        self.assertEqual(report.exit_code(), 0, "an inert gate is reported, not turned into a failure")

    def test_a_gate_that_rejects_a_correct_implementation_is_counted(self) -> None:
        standard(
            self.root,
            c="// REJECT:lint\n",
            m1="// REJECT:trace\n",
            s1="// REJECT:trace\n",
        )
        with_gates(self.root, ["trace", "lint"])
        report = calibrate(load_corpus(self.root), run=gated_run())

        self.assertEqual(report.contribution()["lint"]["false_reject"], 1)
        self.assertEqual(report.contribution()["trace"]["false_reject"], 0)
        self.assertEqual(report.exit_code(), 1)


class TestLintGate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "package"
        shutil.copytree(TASK, self.root)

    def test_the_shipped_task_package_lints_clean_and_passes(self) -> None:
        result = lint_gate(TASK)
        self.assertEqual(result.status, "pass", result.reason)
        self.assertGreater(result.detail["laws"], 0)

    def test_a_finding_fails_and_quotes_the_rule_that_fired(self) -> None:
        manifest = self.root / "laws.manifest.yaml"
        text = manifest.read_text(encoding="utf-8")
        manifest.write_text(text.replace("    priority: core\n", "", 1), encoding="utf-8")

        result = lint_gate(self.root)

        self.assertEqual(result.status, "fail")
        self.assertIn("L012", result.reason)
        self.assertEqual(result.detail["findings"], ["L012"])

    def test_a_submission_without_a_package_is_a_failure_naming_the_manifest(self) -> None:
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        result = lint_gate(empty)

        self.assertEqual(result.status, "fail")
        self.assertIn("laws.manifest.yaml", result.reason)

    def test_a_path_the_linter_cannot_read_is_a_skip_with_a_reason(self) -> None:
        from bendeda.laws.lint import Report

        result = lint_gate(self.root, lint=lambda paths, mutation=None: Report())

        self.assertEqual(result.status, "skip")
        self.assertIn("no package", result.reason)

    def test_a_mutation_report_reaches_the_linter_and_L006_decides(self) -> None:
        # The report is the only thing that makes L006 run at all, so a gate that
        # drops it reports a clean package it never checked for sensitivity.
        (self.root / "mutation.json").write_text(
            json.dumps(
                {
                    "laws": {
                        "fifo_f12_idle_preserves_head": {"killed_by": 0, "total": 4},
                        "fifo_s01_count_within_depth": {"killed_by": 3, "total": 4},
                    }
                }
            ),
            encoding="utf-8",
        )

        result = lint_gate(self.root)

        self.assertEqual(result.status, "fail")
        self.assertIn("L006", result.reason)
        self.assertIn("fifo_f12_idle_preserves_head", result.reason)

    def test_an_unreadable_mutation_report_is_a_failure_naming_the_file(self) -> None:
        (self.root / "mutation.json").write_text("{not json", encoding="utf-8")

        result = lint_gate(self.root)

        self.assertEqual(result.status, "fail")
        self.assertIn("mutation.json", result.reason)


class TestSimulationTimeouts(unittest.TestCase):
    """A hung simulator is a decided entry, and the run ends when the limit does.

    The hang here is a real child process that sleeps, and the deadline is a real
    `subprocess.run(timeout=...)`: what is substituted is the container command, not
    the clock. The model is not compiled, because a timeout says nothing about it.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def hung(self, argv, **kwargs):
        """Stand in for a container that never returns, with the real deadline."""
        return subprocess.run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            capture_output=True,
            text=True,
            timeout=kwargs.get("timeout"),
        )

    def test_the_configured_timeout_reaches_the_simulator(self) -> None:
        submissions(self.root)
        seen: dict = {}

        def simulate(rtl, manifest, plan, **kwargs):
            seen.update(kwargs)
            return [1, 2]

        trace_gate(
            self.root,
            {"sim_timeout": 3},
            toolchain=toolchain,
            available=lambda *_: True,
            compile_fn=lambda *a, **k: Compile(),
            vectors=lambda *a, **k: {"steps": [{"out": 1}, {"out": 2}]},
            simulate=simulate,
        )

        self.assertEqual(seen.get("timeout"), 3.0)

    def test_a_hung_simulation_fails_its_entry_and_the_calibration_exits_1(self) -> None:
        standard(self.root)
        removed: list[list[str]] = []
        simulate = simulate_verilator

        def remove(argv, **kwargs):
            removed.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, "", "")

        def run(artifacts, names, cfg):
            return {
                name: trace_gate(
                    artifacts,
                    cfg,
                    toolchain=toolchain,
                    available=lambda *_: True,
                    compile_fn=lambda *a, **k: Compile(),
                    vectors=lambda *a, **k: {"steps": [{"out": 1}]},
                    # The real simulator, with the container command replaced by
                    # something that hangs and the real removal hook recorded.
                    simulate=lambda rtl, manifest, plan, **kwargs: simulate(
                        rtl,
                        manifest,
                        plan,
                        runner=self.hung,
                        remove=remove,
                        **kwargs,
                    ),
                )
                for name in names
            }

        started = time.monotonic()
        report = calibrate(load_corpus(self.root), {"sim_timeout": 0.2}, run=run)
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 30, "a hung entry must not hold the calibration until it sleeps out")
        self.assertEqual(report.exit_code(), 1, "the gates ran and failed; that is not 'uncalibrated'")
        self.assertEqual(report.undecidable(), [], "a timeout is decided, not undecidable")
        self.assertTrue(all(entry.verdict == "rejected" for entry in report.entries))
        self.assertIn("did not finish within", report.entries[0].reason or "")
        self.assertTrue(
            any(argv[:3] == ["docker", "rm", "-f"] and argv[3].startswith("bendeda-dut-")
                for argv in removed),
            "the simulated container is removed, because killing the client is not enough",
        )


class TestCorpusFixtureCollateral(unittest.TestCase):
    """The fixture's SVA pack must stay attached to the law package it translates.

    L011 accepts a `translation` on its presence alone, so a renamed assertion, a
    pack that stops declaring it, or a job that stops reading the pack would leave
    `lint` clean and `formal` proving nothing. This is the link the linter cannot
    check and the gate would report as a vacuous pass.
    """

    root = (
        Path(__file__).resolve().parents[1]
        / "experiments"
        / "fixtures"
        / "toy_counter_laws"
    )

    def test_every_declared_translation_names_a_label_in_the_pack(self) -> None:
        from bendeda.laws.manifest import Manifest

        manifest = Manifest.load(self.root / "laws.manifest.yaml")
        pack = (self.root / "props.sv").read_text(encoding="utf-8")
        declared = [
            (entry.translation or {}).get("sva") for entry in manifest.laws
        ]
        declared = [name for name in declared if name]
        self.assertGreaterEqual(len(declared), 5, "every transferable law names one")
        for name in declared:
            self.assertIn(f"{name}:", pack, f"{name} is declared but not asserted")

    def test_the_job_reads_the_dut_and_the_pack(self) -> None:
        job = (self.root / "counter.sby").read_text(encoding="utf-8")
        self.assertIn("read_verilog", job)
        self.assertIn("dut.sv", job)
        self.assertIn("props.sv", job)
        self.assertIn("prep -top toy_counter_props", job)


class TestB1VariantCollateral(unittest.TestCase):
    """The declared B1 variants and the corpus entries that measure them.

    `variants.yaml` declares eight seeded bugs. LA4 is measured against the corpus,
    not against the declaration, so a tag with no entry is an unmeasured claim and
    an entry whose tag was renamed is a bug nobody declared. Neither shows up as a
    gate failure — the corpus would still calibrate — which is why the two lists
    are checked against each other here.
    """

    root = Path(__file__).resolve().parents[1]
    corpus = root / "experiments" / "corpus" / "b1_fifo_rtl"
    variants = root / "tasks" / "seq" / "B1_fifo" / "variants.yaml"

    def _declared(self) -> dict[str, str]:
        """Tag -> entry directory, or "" when the tag has no entry.

        Line-based on purpose: `variants.yaml` is read by people and by this test,
        not by a manifest loader, so pulling in a YAML parser would test the parser.
        """
        tags: dict[str, str] = {}
        current: str | None = None
        for line in self.variants.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text.startswith("- tag: "):
                current = text[len("- tag: "):]
                tags[current] = ""
            elif current and text.startswith("entry: "):
                value = text[len("entry: "):]
                tags[current] = "" if value in ("null", "~") else value
        return tags

    def test_the_declared_tags_and_the_entries_agree(self) -> None:
        declared = self._declared()
        self.assertEqual(len(declared), 8, "the eight tags Appendix G lists")
        entries = {value for value in declared.values() if value}
        corpus = json.loads((self.corpus / "corpus.json").read_text(encoding="utf-8"))
        staged = {
            entry["artifacts"]
            for entry in corpus["entries"]
            if entry["id"].startswith("v")
        }
        self.assertEqual(
            {Path(value).as_posix() for value in entries},
            {Path(f"experiments/corpus/b1_fifo_rtl/{name}").as_posix() for name in staged},
        )

    def test_each_variant_entry_marks_its_own_edit(self) -> None:
        for tag, entry in self._declared().items():
            if not entry:
                continue
            text = (self.root / entry / "dut.sv").read_text(encoding="utf-8")
            self.assertIn(f"VARIANT {tag}", text, f"{entry} does not say it is {tag}")
            self.assertIn("module b1_fifo", text)

    def test_a_tag_without_an_entry_records_why(self) -> None:
        text = self.variants.read_text(encoding="utf-8")
        missing = [tag for tag, entry in self._declared().items() if not entry]
        for tag in missing:
            self.assertIn(f"tag: {tag}", text)
        self.assertIn("entry: null", text, "an unmeasured tag says so rather than being dropped")
        self.assertIn("reason:", text, "and gives the reason it cannot be measured")


class TestRegistry(unittest.TestCase):
    def test_the_registry_names_the_gates_that_execute(self) -> None:
        self.assertEqual(sorted(GATES), ["formal", "lint", "trace"])

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
