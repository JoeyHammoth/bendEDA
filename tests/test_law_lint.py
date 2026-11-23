# SPDX-License-Identifier: Apache-2.0
"""Law lint (issue #10, exit criterion 5).

The fixture package seeds one defect per rule, and the main assertion is on the
*set* of rules that fired. A rule that stops firing fails here instead of
producing a shorter report nobody reads; a rule that fires on the clean package
fails too, because a gate that refuses everything is as useless as one that
accepts everything.
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from bendeda.laws import RULES, discover, run
from bendeda.laws.manifest import ManifestError, parse_text
from bendeda.laws.rules import expected_name
from bendeda.laws.source import parse

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "law_packages"
DEFECTIVE = FIXTURES / "defective"
NL = chr(10)

CLEAN_LAWS = NL.join(
    [
        "import Base",
        "",
        "law toy_s01_count_le_depth:",
        "  for c: U32",
        "  {U32.add(c, 0) == c : U32}",
        "",
        "def toy_s01_count_le_depth(c):",
        "  {==}",
        "",
        "law toy_f01_add_zero:",
        "  for a: U32",
        "  {U32.sub(a, a) == 0 : U32}",
        "",
        "def toy_f01_add_zero(a):",
        "  {==}",
        "",
    ]
)

CLEAN_MODEL = NL.join(
    [
        "import Base",
        "",
        "def toy_step(x: U32) -> U32:",
        "  U32.add(x, 1)",
        "",
    ]
)

CLEAN_MANIFEST = NL.join(
    [
        "task: T9_toy",
        'bend_version: "2.0.40"',
        "requirements: [R1, R2]",
        "",
        "laws:",
        "  - id: TOY-S-01",
        "    name: toy_s01_count_le_depth",
        "    class: L-SAFE",
        "    priority: core",
        "    requirements: [R1]",
        "    witness: null",
        "    translation: {sva: p_count, template: invariant_v1}",
        "    status: draft",
        "  - id: TOY-F-01",
        "    name: toy_f01_add_zero",
        "    class: L-FUNC",
        "    priority: important",
        "    requirements: [R2]",
        "    witness: toy_w01_reaches_zero",
        "    translation: {sva: p_zero, template: implication_v1}",
        "    status: draft",
        "",
        "conformance_only_requirements: []",
        "oracle_only_requirements: []",
        "",
        "hashes:",
        "  LAWS.bend: __LAWS__",
        "  model.bend: __MODEL__",
        "",
    ]
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_clean_package(root: Path) -> None:
    (root / "LAWS.bend").write_text(CLEAN_LAWS, encoding="utf-8", newline="")
    (root / "model.bend").write_text(CLEAN_MODEL, encoding="utf-8", newline="")
    manifest = (
        CLEAN_MANIFEST.replace("__LAWS__", digest(root / "LAWS.bend"))
        .replace("__MODEL__", digest(root / "model.bend"))
    )
    (root / "laws.manifest.yaml").write_text(manifest, encoding="utf-8", newline="")
    provenance = NL.join(
        [
            "task: T9_toy",
            "artifacts:",
            "  - path: LAWS.bend",
            f"    sha256: {digest(root / 'LAWS.bend')}",
            "  - path: model.bend",
            f"    sha256: {digest(root / 'model.bend')}",
            "",
        ]
    )
    (root / "provenance.yaml").write_text(provenance, encoding="utf-8", newline="")


MUTATION = {"laws": {"toy_s01_count_le_depth": {"killed_by": 2, "total": 4},
                     "toy_f01_add_zero": {"killed_by": 1, "total": 4}}}


class TestDefectiveFixture(unittest.TestCase):
    def test_every_rule_fires_and_none_goes_missing(self) -> None:
        report = run([str(DEFECTIVE)], mutation={"laws": {
            "toy_s01_count_le_depth": {"killed_by": 0, "total": 6},
            "toy_s05_conjunction": {"killed_by": 2, "total": 6},
        }})
        fired = {finding.rule for finding in report.findings}
        self.assertEqual(fired, set(RULES), msg=sorted(fired))
        self.assertEqual(report.exit_code(), 1)

    def test_the_report_names_the_law_and_the_line(self) -> None:
        report = run([str(DEFECTIVE)], mutation={"laws": {"toy_s01_count_le_depth": {"killed_by": 0}}})
        l008 = [f for f in report.findings if f.rule == "L008"]
        self.assertTrue(l008)
        self.assertEqual(l008[0].law, "toy_bad_name_9x")
        self.assertEqual(l008[0].path, "laws.manifest.yaml")

    def test_lint_without_a_mutation_report_says_l006_did_not_run(self) -> None:
        report = run([str(DEFECTIVE)])
        self.assertNotIn("L006", {finding.rule for finding in report.findings})
        self.assertTrue(any("L006 not evaluated" in note for note in report.notes))


class TestCleanPackage(unittest.TestCase):
    def test_a_clean_package_has_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "clean"
            root.mkdir()
            write_clean_package(root)
            report = run([str(root)], mutation=MUTATION)
            self.assertEqual([f.render() for f in report.findings], [])
            self.assertEqual(report.exit_code(), 0)
            self.assertEqual(report.laws, 2)
            # Every applicable rule ran: no note may say one was skipped.
            self.assertEqual([n for n in report.notes if "not evaluated" in n], [])

    def test_an_empty_directory_is_not_a_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run([tmp])
            self.assertEqual(report.exit_code(), 3)
            self.assertEqual(report.findings, [])
            self.assertTrue(report.skipped)


class TestDiscovery(unittest.TestCase):
    def test_a_directory_with_one_package_is_found(self) -> None:
        roots, skipped = discover([str(DEFECTIVE)])
        self.assertEqual(roots, [DEFECTIVE])
        self.assertEqual(skipped, [])

    def test_a_bend_file_is_not_a_package(self) -> None:
        roots, skipped = discover([str(DEFECTIVE / "LAWS.bend")])
        self.assertEqual(roots, [])
        self.assertEqual(len(skipped), 1)


class TestManifestReader(unittest.TestCase):
    def test_flow_collections_and_null(self) -> None:
        raw = parse_text(
            "task: T9_toy\n"
            "requirements: [R1, R2]\n"
            "laws:\n"
            "  - id: TOY-S-01\n"
            "    translation: {sva: p_count, template: invariant_v1}\n"
            "    witness: null\n"
        )
        self.assertEqual(raw["requirements"], ["R1", "R2"])
        self.assertEqual(raw["laws"][0]["translation"]["sva"], "p_count")
        self.assertIsNone(raw["laws"][0]["witness"])

    def test_a_tab_is_refused_rather_than_guessed(self) -> None:
        with self.assertRaises(ManifestError):
            parse_text("task: T9_toy\n\tlaws: []\n")

    def test_an_unclosed_flow_list_is_refused(self) -> None:
        with self.assertRaises(ManifestError):
            parse_text("task: T9_toy\nrequirements: [R1, R2\n")


class TestSourceReader(unittest.TestCase):
    def test_a_multiline_claim_and_a_hypothesis(self) -> None:
        parsed = parse(
            "import Base\n"
            "law toy_s01_guard:\n"
            "  for x: U32\n"
            "  for h : {x == x : U32}\n"
            "  {U32.add(x, 0)\n"
            "    == x : U32}\n"
            "def toy_s01_guard(x, h):\n"
            "  {==}\n"
        )
        law = parsed.laws[0]
        self.assertEqual(law.claim, "U32.add(x, 0) == x")
        self.assertEqual(law.claim_type, "U32")
        self.assertTrue(law.params[1].hypothesis)
        self.assertTrue(law.conditional)
        self.assertEqual(law.line, 2)
        self.assertEqual(parsed.defs[0].params, ("x", "h"))

    def test_an_unclosed_claim_is_a_problem_not_a_guess(self) -> None:
        parsed = parse("law toy_s01_bad:\n  {U32.add(1, 1) == 2 : U32\n")
        self.assertTrue(parsed.problems)
        self.assertIn("never closed", parsed.problems[0])


class TestNaming(unittest.TestCase):
    def test_the_convention_maps_id_to_prefix(self) -> None:
        self.assertEqual(expected_name("T9_toy", "TOY-S-09"), "toy_s09_")
        self.assertIsNone(expected_name("T9_toy", "not-an-id"))


if __name__ == "__main__":
    unittest.main()
