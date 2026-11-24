# SPDX-License-Identifier: Apache-2.0
"""Sealed-oracle commit-reveal (issue #13).

The commitment is only worth anything if three things hold, and each is tested
directly:

* the archive is deterministic, so two hosts seal to the same root;
* verification needs no decryption, and fails on a one-byte change;
* sealing refuses rather than writing a plaintext archive when it cannot encrypt.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from bendeda import oracle
from bendeda.cli import main

ROOT = Path(__file__).resolve().parents[1]
NL = chr(10)

FAKE_AGE = NL.join(
    [
        "import pathlib, sys",
        "args = sys.argv[1:]",
        "target = pathlib.Path(args[args.index('-o') + 1])",
        "data = sys.stdin.buffer.read()",
        "target.write_bytes(b'FAKEAGE' + data)",
        "",
    ]
)


def write_pack(root: Path, order: str = "forward", stamp: int = 1) -> None:
    pack = root / "pack"
    pack.mkdir(parents=True, exist_ok=True)
    items = [("a.bend", "law a:" + NL + "  {0n == 0n : Nat}" + NL),
             ("b.bend", "law b:" + NL + "  {1n == 1n : Nat}" + NL)]
    if order == "reverse":
        items.reverse()
    for name, text in items:
        path = pack / name
        path.write_text(text, encoding="utf-8", newline="")
        # A different mtime on every build: the archive must not record it.
        import os

        os.utime(path, (stamp, stamp))


def ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


class TestDeterministicArchive(unittest.TestCase):
    def test_two_builds_of_the_same_content_agree_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            write_pack(Path(first), order="forward", stamp=1)
            write_pack(Path(second), order="reverse", stamp=987654321)
            # Both trees are named `pack`, so the tar member names agree.
            self.assertEqual(
                oracle.canonical_tar(Path(first) / "pack"),
                oracle.canonical_tar(Path(second) / "pack"),
            )
            self.assertEqual(
                oracle.build_commitment(Path(first) / "pack").root,
                oracle.build_commitment(Path(second) / "pack").root,
            )

    def test_the_archive_records_no_timestamp_or_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_pack(Path(tmp))
            archive = oracle.canonical_tar(Path(tmp) / "pack")
            self.assertNotIn(b"987654321", archive)
            self.assertIn(b"a.bend", archive)

    def test_one_changed_byte_changes_the_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            write_pack(Path(tmp))
            before = oracle.build_commitment(pack).root
            (pack / "a.bend").write_text("law a:" + NL + "  {0n == 1n : Nat}" + NL, encoding="utf-8", newline="")
            after = oracle.build_commitment(pack).root
            self.assertNotEqual(before, after)

    def test_an_empty_directory_has_no_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(oracle.OracleError):
                oracle.merkle_root({})


class TestCompare(unittest.TestCase):
    def test_an_unchanged_tree_has_no_differences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            write_pack(Path(tmp))
            commitment = oracle.build_commitment(pack)
            self.assertEqual(oracle.compare(pack, commitment), [])

    def test_a_changed_file_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            write_pack(Path(tmp))
            commitment = oracle.build_commitment(pack)
            (pack / "b.bend").write_text("law b:" + NL + "  {2n == 2n : Nat}" + NL, encoding="utf-8", newline="")
            differences = oracle.compare(pack, commitment)
            self.assertEqual([d.name for d in differences], ["b.bend"])
            self.assertIn("now", differences[0].render())

    def test_an_added_and_a_missing_file_are_both_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            write_pack(Path(tmp))
            commitment = oracle.build_commitment(pack)
            (pack / "a.bend").unlink()
            (pack / "c.bend").write_text("law c:" + NL, encoding="utf-8", newline="")
            rendered = sorted(d.render() for d in oracle.compare(pack, commitment))
            self.assertTrue(any("missing" in line for line in rendered))
            self.assertTrue(any("added" in line for line in rendered))


class TestSealAndVerify(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "oracle"
        self.pack = self.root / "pack"
        write_pack(self.root)
        self.out = Path(self.tmp.name) / "sealed"
        self.age = Path(self.tmp.name) / "fake_age.py"
        self.age.write_text(FAKE_AGE, encoding="utf-8", newline="")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_a_dry_run_writes_nothing(self) -> None:
        commitment, target = oracle.seal(self.pack, self.out, None, dry_run=True)
        self.assertIsNone(target)
        self.assertFalse(self.out.exists())
        self.assertEqual(commitment.root, oracle.build_commitment(self.pack).root)

    def test_no_recipient_refuses_rather_than_writing_plaintext(self) -> None:
        with self.assertRaises(oracle.OracleError):
            oracle.seal(self.pack, self.out, None)
        self.assertFalse(self.out.exists())

    def test_no_age_refuses(self) -> None:
        with self.assertRaises(oracle.OracleError):
            oracle.seal(self.pack, self.out, "age1example", age="definitely-not-age")
        self.assertFalse(self.out.exists())

    def test_seal_writes_ciphertext_a_commitment_and_sums(self) -> None:
        commitment, target = oracle.seal(
            self.pack, self.out, "age1example", age=[sys.executable, str(self.age)]
        )
        self.assertIsNotNone(target)
        assert target is not None
        self.assertTrue(target.name.endswith(".tar.age"))
        self.assertTrue(target.read_bytes().startswith(b"FAKEAGE"))
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         ["SHA256SUMS", "commitment.json", "pack.tar.age"])
        stored = json.loads((self.out / oracle.COMMITMENT_NAME).read_text(encoding="utf-8"))
        self.assertEqual(stored["root"], commitment.root)
        self.assertEqual(stored["leaf_count"], 2)
        sums = (self.out / "SHA256SUMS").read_text(encoding="utf-8").split()
        self.assertEqual(sums[1], target.name)
        self.assertEqual(sums[0], hashlib.sha256(target.read_bytes()).hexdigest())

    def test_verification_passes_and_fails_on_one_byte(self) -> None:
        commitment, _ = oracle.seal(
            self.pack, self.out, "age1example", age=[sys.executable, str(self.age)]
        )
        path = self.out / oracle.COMMITMENT_NAME
        code = oracle.cmd_verify_commitment(ns(path=str(self.pack), commitment=str(path)))
        self.assertEqual(code, oracle.EXIT_OK, msg=commitment.root)

        (self.pack / "a.bend").write_bytes((self.pack / "a.bend").read_bytes() + b" ")
        code = oracle.cmd_verify_commitment(ns(path=str(self.pack), commitment=str(path)))
        self.assertEqual(code, oracle.EXIT_FAILED)

    def test_the_cli_path_verifies_without_decrypting(self) -> None:
        oracle.seal(self.pack, self.out, "age1example", age=[sys.executable, str(self.age)])
        path = self.out / oracle.COMMITMENT_NAME
        code = main(["oracle", "verify-commitment", str(self.pack), "--commitment", str(path)])
        self.assertEqual(code, 0)

    def test_a_missing_commitment_is_exit_three(self) -> None:
        code = oracle.cmd_verify_commitment(
            ns(path=str(self.pack), commitment=str(self.out / "nope.json"))
        )
        self.assertEqual(code, oracle.EXIT_NOTHING)


class TestCanaryGuard(unittest.TestCase):
    GUID = "9f6e2c1a-73b5-4d08-a1e4-5c2b8f0d7a36"

    def run_guard(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" / "check_oracle_absence.py"), str(root)],
            capture_output=True,
            text=True,
        )

    def test_the_repository_is_clean(self) -> None:
        result = self.run_guard(ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_canary_in_a_task_file_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "oracle_sealed").mkdir()
            (root / "oracle_sealed" / "canary.txt").write_text(
                "# canary" + NL + "guid: " + self.GUID + NL, encoding="utf-8", newline=""
            )
            (root / "tasks" / "A").mkdir(parents=True)
            (root / "tasks" / "A" / "spec.md").write_text("clean" + NL, encoding="utf-8", newline="")
            self.assertEqual(self.run_guard(root).returncode, 0)

            (root / "tasks" / "A" / "leak.md").write_text(
                "the pack contains " + self.GUID + NL, encoding="utf-8", newline=""
            )
            result = self.run_guard(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("canary GUID", result.stderr)

    def test_a_canary_file_without_a_guid_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "oracle_sealed").mkdir()
            (root / "oracle_sealed" / "canary.txt").write_text("nothing here" + NL, encoding="utf-8", newline="")
            result = self.run_guard(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("no canary GUID", result.stderr)


class TestRecordResult(unittest.TestCase):
    """The receiving end of the O contract: the scoring host's answer, checked."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bundle = Path(self.tmp.name) / "bundle"
        self.bundle.mkdir()
        (self.bundle / "events.jsonl").write_text(
            json.dumps(
                {"seq": 1, "tool": "submit", "resource": "t/submission", "action": "allow"}
            )
            + NL,
            encoding="utf-8",
        )

    def test_a_result_is_recorded_and_becomes_o(self) -> None:
        from bendeda.score import load as load_bundle, report

        target = oracle.record_result(self.bundle, {"c1": True}, host="scoring-1")
        stored = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(stored["host"], "scoring-1")
        self.assertEqual(stored["scheme"], oracle.RESULT_SCHEME)

        scored = report(load_bundle(self.bundle))
        self.assertEqual(scored.score.O, 1, scored.score.reason)
        self.assertIn("all 1 oracle components passed", scored.score.reason)
        self.assertIsNone(scored.score.V, "V is still absent: no gate result was recorded")

    def test_a_second_result_is_refused(self) -> None:
        oracle.record_result(self.bundle, {"c1": True}, host="scoring-1")
        with self.assertRaises(oracle.OracleError):
            oracle.record_result(self.bundle, {"c1": False}, host="scoring-2")

    def test_a_run_that_did_not_submit_has_no_oracle_result(self) -> None:
        (self.bundle / "events.jsonl").write_text("", encoding="utf-8")
        with self.assertRaises(oracle.OracleError):
            oracle.record_result(self.bundle, {"c1": True}, host="scoring-1")
        self.assertFalse((self.bundle / oracle.RESULT_NAME).exists())

    def test_a_void_run_is_refused(self) -> None:
        with (self.bundle / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"seq": 0, "tool": "infra", "resource": "daemon died"}) + NL)
        with self.assertRaises(oracle.OracleError):
            oracle.record_result(self.bundle, {"c1": True}, host="scoring-1")

    def test_components_must_be_booleans(self) -> None:
        with self.assertRaises(oracle.OracleError):
            oracle.record_result(self.bundle, {"c1": "true"}, host="scoring-1")

    def test_an_empty_or_unnamed_result_is_refused(self) -> None:
        with self.assertRaises(oracle.OracleError):
            oracle.record_result(self.bundle, {}, host="scoring-1")
        with self.assertRaises(oracle.OracleError):
            oracle.record_result(self.bundle, {"c1": True}, host="  ")

    def test_the_cli_path_records_and_refuses_a_second_time(self) -> None:
        components = Path(self.tmp.name) / "components.json"
        components.write_text(json.dumps({"c1": True}), encoding="utf-8")
        argv = [
            "oracle", "record", "--bundle", str(self.bundle),
            "--components", str(components), "--host", "scoring-1",
        ]
        self.assertEqual(main(argv), 0)
        self.assertEqual(main(argv), oracle.EXIT_NOTHING)


class TestScorePack(unittest.TestCase):
    """The scoring host's half: prove the pack is the sealed one, then let it answer."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.bundle = root / "bundle"
        self.bundle.mkdir()
        (self.bundle / "events.jsonl").write_text(
            json.dumps(
                {"seq": 1, "tool": "submit", "resource": "t/submission", "action": "allow"}
            )
            + NL,
            encoding="utf-8",
        )
        self.pack = root / "pack"
        self.pack.mkdir()
        (self.pack / "a.bend").write_text("law a:" + NL, encoding="utf-8", newline="")
        self.commitment = root / "commitment.json"
        self.write_scorer("print('{\"c1\": true}')")

    def write_scorer(self, body: str) -> None:
        """Write the pack's scorer and re-sign the commitment over the new pack.

        The scorer is part of the pack, so a test that changes it has to publish a
        commitment that matches — otherwise it would be testing the tamper check.
        """
        (self.pack / oracle.SCORER_NAME).write_text(body + NL, encoding="utf-8", newline="")
        self.commitment.write_text(
            oracle.build_commitment(self.pack).as_json(), encoding="utf-8", newline=""
        )
        self.root = oracle.load_commitment(self.commitment).root

    def score(self, *extra: str) -> int:
        return main([
            "oracle", "score",
            "--pack", str(self.pack),
            "--commitment", str(self.commitment),
            "--bundle", str(self.bundle),
            "--host", "scoring-1",
            *extra,
        ])

    def test_the_sealed_pack_scores_and_becomes_o(self) -> None:
        from bendeda.score import load as load_bundle, report

        self.write_scorer("print('{\"components\": {\"c1\": true, \"c2\": false}}')")
        self.assertEqual(self.score(), 0)
        stored = json.loads((self.bundle / oracle.RESULT_NAME).read_text(encoding="utf-8"))
        self.assertEqual(stored["host"], "scoring-1")
        self.assertEqual(stored["commitment_root"], self.root)
        self.assertNotIn(
            "pack_version", stored, "a pack that publishes no version must not acquire one"
        )

        scored = report(load_bundle(self.bundle))
        self.assertEqual(scored.score.O, 0, scored.score.reason)
        self.assertIn("oracle components failed: c2", scored.score.reason)

    def test_the_pack_version_travels_with_the_result(self) -> None:
        from bendeda.score import load as load_bundle, report

        (self.pack / oracle.VERSION_NAME).write_text("0.4.2-rc1" + NL, encoding="utf-8", newline="")
        # VERSION is a component like any other, so publishing it re-signs the pack.
        self.write_scorer("print('{\"c1\": true}')")
        self.assertEqual(self.score(), 0)

        stored = json.loads((self.bundle / oracle.RESULT_NAME).read_text(encoding="utf-8"))
        self.assertEqual(stored["pack_version"], "0.4.2-rc1")
        self.assertEqual(stored["commitment_root"], self.root)
        self.assertEqual(
            report(load_bundle(self.bundle)).as_json()["oracle"],
            {
                "host": "scoring-1",
                "scheme": oracle.RESULT_SCHEME,
                "commitment_root": self.root,
                "pack_version": "0.4.2-rc1",
            },
        )

    def test_a_tampered_pack_is_not_scored(self) -> None:
        (self.pack / "a.bend").write_bytes((self.pack / "a.bend").read_bytes() + b" ")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(self.score(), oracle.EXIT_NOTHING)
        self.assertIn("not the sealed one", err.getvalue())
        self.assertIn("a.bend", err.getvalue())
        self.assertFalse((self.bundle / oracle.RESULT_NAME).exists())

    def test_a_pack_that_crashes_writes_nothing(self) -> None:
        self.write_scorer("raise SystemExit('pack exploded')")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(self.score(), oracle.EXIT_NOTHING)
        self.assertIn("exited", err.getvalue())
        self.assertFalse((self.bundle / oracle.RESULT_NAME).exists())

    def test_a_pack_that_prints_no_json_writes_nothing(self) -> None:
        self.write_scorer("print('looks fine to me')")
        self.assertEqual(self.score(), oracle.EXIT_NOTHING)
        self.assertFalse((self.bundle / oracle.RESULT_NAME).exists())

    def test_non_boolean_components_are_refused(self) -> None:
        self.write_scorer("print('{\"c1\": \"true\"}')")
        self.assertEqual(self.score(), oracle.EXIT_NOTHING)
        self.assertFalse((self.bundle / oracle.RESULT_NAME).exists())

    def test_relative_paths_score_like_absolute_ones(self) -> None:
        """The scorer runs inside the pack, so a relative path must not resolve twice."""
        self.write_scorer("print('{\"c1\": true}')")
        previous = Path.cwd()
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, previous)
        code = main([
            "oracle", "score",
            "--pack", "pack",
            "--commitment", "commitment.json",
            "--bundle", "bundle",
            "--host", "scoring-1",
        ])
        self.assertEqual(code, 0)
        self.assertTrue((self.bundle / oracle.RESULT_NAME).is_file())

    def test_a_pack_that_never_answers_is_refused(self) -> None:
        self.write_scorer("import time; time.sleep(5)")
        started = time.monotonic()
        with self.assertRaises(oracle.OracleError) as caught:
            oracle.pack_components(self.pack, self.bundle, timeout=0.2)
        self.assertIn("did not answer", str(caught.exception))
        self.assertLess(time.monotonic() - started, 4.0, "the timeout, not the sleep, ended it")

    def test_the_second_score_is_a_disagreement_not_an_update(self) -> None:
        self.assertEqual(self.score(), 0)
        self.assertEqual(self.score(), oracle.EXIT_NOTHING)


class TestDemoPack(unittest.TestCase):
    """The committed stand-in pack is only useful while it matches its commitment."""

    PACK = ROOT / "experiments" / "fixtures" / "demo_pack"
    COMMITMENT = ROOT / "experiments" / "fixtures" / "demo_pack.commitment.json"

    def test_the_pack_matches_its_commitment(self) -> None:
        commitment = oracle.load_commitment(self.COMMITMENT)
        self.assertEqual([d.render() for d in oracle.compare(self.PACK, commitment)], [])

    def test_the_stand_in_pack_names_its_version(self) -> None:
        self.assertEqual(oracle.pack_version(self.PACK), "0.0.1-demo")

    def test_it_scores_a_bundle_with_a_submission_and_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle"
            bundle.mkdir()
            (bundle / "events.jsonl").write_text(
                json.dumps(
                    {"seq": 1, "tool": "submit", "resource": "x", "action": "allow"}
                )
                + NL,
                encoding="utf-8",
            )
            (bundle / "gates.json").write_text(json.dumps({"trace": True}), encoding="utf-8")
            components = oracle.pack_components(self.PACK, bundle)
        self.assertEqual(
            components, {"permitted submission": True, "gate results recorded": True}
        )

    def test_an_unscored_bundle_is_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle"
            bundle.mkdir()
            (bundle / "events.jsonl").write_text("", encoding="utf-8")
            components = oracle.pack_components(self.PACK, bundle)
        self.assertEqual(
            components, {"permitted submission": False, "gate results recorded": False}
        )


if __name__ == "__main__":
    unittest.main()
