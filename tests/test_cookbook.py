# SPDX-License-Identifier: Apache-2.0
"""The proof cookbook and the PEH list (issue #11).

Three properties, each of which fails loudly:

* every example checks under the pinned checker, except the one example that is
  meant to be refused as a counterexample;
* the PEH list is consumed by L007 and every entry fires on a real construct;
* the prose cookbook documents every example and every PEH id, so the two do not
  drift apart.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import unittest
from pathlib import Path

from bendeda.laws import peh
from bendeda.laws.rules import Package, l007_escape_hatches
from bendeda.laws.source import parse

ROOT = Path(__file__).resolve().parents[1]
COOKBOOK = ROOT / "docs" / "cookbook"
DOC = ROOT / "docs" / "proof_cookbook.md"
NL = chr(10)

#: Per file: the laws it contains, and whether the file is expected to check.
EXPECTED = {
    "s1_direct.bend": 4,
    "s2_case.bend": 3,
    "s3_induction.bend": 2,
    "s4_invariant.bend": 2,
    "s5_rewrite.bend": 4,
    "s6_factoring.bend": 4,
    "s7_refinement.bend": 1,
    "s8_unroll.bend": 2,
    "s9_counterexample.bend": 1,
}
EXPECT_FAIL = {"s9_counterexample.bend"}


def bend_command() -> list[str] | None:
    bun = os.environ.get("BENDEDA_BUN")
    cli = os.environ.get("BENDEDA_BEND_CLI")
    if bun and cli and Path(cli).exists():
        return [bun, cli]
    found = shutil.which("bend")
    return [found] if found else None


def issue(package: Package) -> list[str]:
    findings: list[str] = []
    l007_escape_hatches(package, findings)  # type: ignore[arg-type]
    return [f.render() for f in findings]


class TestPehList(unittest.TestCase):
    def test_every_entry_has_a_unique_id_and_a_reason(self) -> None:
        ids = [entry.id for entry in peh.PEH]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, [f"PEH-{n:02d}" for n in range(1, len(ids) + 1)])
        for entry in peh.PEH:
            self.assertTrue(entry.why.strip())
            self.assertTrue(entry.instead.strip())

    def test_each_construct_is_recognised(self) -> None:
        samples = {
            "PEH-01": "def f(x: U32) -> U32:" + NL + "  x",
            "PEH-02": "def f?(x: U32) -> U32:" + NL + "  x",
            "PEH-03": "law l:" + NL + "  ?TODO",
            "PEH-04": "law l:" + NL + "  ?goal",
            "PEH-05": "def f() -> U32:" + NL + '  import "native"',
            "PEH-06": "def f(a) -> U32:" + NL + "  Array.get_unchecked(U32, a, 0)",
            "PEH-07": "def f(x: U32) -> U32:" + NL + "  x # TODO: widen",
        }
        samples["PEH-01"] = "@unsafe" + NL + samples["PEH-01"]
        for identifier, source in samples.items():
            hit = peh.by_id(identifier)
            matches = any(hit.regex.search(line) for line in source.splitlines())
            self.assertTrue(matches, f"{identifier} did not match its own sample")

    def test_a_todo_hole_is_not_double_counted_as_a_marker(self) -> None:
        hits = peh.scan("law l:" + NL + "  ?TODO" + NL)
        self.assertEqual([h.entry.id for h in hits], ["PEH-03"])

    def test_comments_are_not_hits(self) -> None:
        self.assertEqual(peh.scan("# never write @unsafe or ?TODO" + NL), [])

    def test_l007_names_the_entry(self) -> None:
        source = "@unsafe" + NL + "def f(x: U32) -> U32:" + NL + "  x" + NL
        package = Package(
            root=ROOT,
            manifest=None,  # type: ignore[arg-type]
            laws=parse(source),
        )
        rendered = issue(package)
        self.assertEqual(len(rendered), 1)
        self.assertIn("PEH-01", rendered[0])
        self.assertIn("@unsafe", rendered[0])


class TestCookbookFiles(unittest.TestCase):
    def test_every_example_file_is_listed_and_holds_the_expected_laws(self) -> None:
        on_disk = {path.name for path in COOKBOOK.glob("*.bend")}
        self.assertEqual(on_disk, set(EXPECTED))
        total = 0
        for name, count in EXPECTED.items():
            parsed = parse((COOKBOOK / name).read_text(encoding="utf-8"))
            self.assertEqual(parsed.problems, [], f"{name}: {parsed.problems}")
            self.assertEqual(len(parsed.laws), count, name)
            total += count
            for law in parsed.laws:
                # Generic examples only: a cookbook law that looked like a task
                # law would be an answer key, not a guide.
                self.assertTrue(law.name.startswith("cook_") or law.name.startswith("aux_"), law.name)
        self.assertGreaterEqual(total, 20)
        self.assertLessEqual(total, 30)

    def test_the_document_lists_every_file_strategy_and_peh(self) -> None:
        self.assertTrue(DOC.exists(), DOC)
        text = DOC.read_text(encoding="utf-8")
        for name in EXPECTED:
            self.assertIn(name, text)
        for number in range(1, 10):
            self.assertIn(f"S{number}", text)
        for entry in peh.PEH:
            self.assertIn(entry.id, text)

    def test_no_example_mentions_a_task(self) -> None:
        for path in COOKBOOK.glob("*.bend"):
            self.assertNotIn("tasks/", path.read_text(encoding="utf-8"), path.name)


class TestCookbookExamplesCheck(unittest.TestCase):
    def setUp(self) -> None:
        self.command = bend_command()
        if self.command is None:
            self.skipTest(
                "no Bend compiler: set BENDEDA_BUN and BENDEDA_BEND_CLI, or put bend on PATH"
            )

    def gate(self, path: Path) -> str:
        argv = self.command + [str(path)]
        try:
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=300)
        except OSError:
            # Windows' npm Bun is a POSIX shim, not a PE image; CI runs Linux.
            shell = " ".join(shlex.quote(part) for part in argv)
            result = subprocess.run(
                ["bash", "-c", shell], cwd=ROOT, capture_output=True, text=True, timeout=300
            )
        return result.stdout + result.stderr

    def test_examples_check_and_the_counterexample_is_refused(self) -> None:
        for name in EXPECTED:
            output = self.gate(COOKBOOK / name)
            if name in EXPECT_FAIL:
                self.assertIn("SOME PROOFS FAIL", output, f"{name}: {output}")
                self.assertNotIn("ALL PROOFS CHECK", output, name)
                # A counterexample must show both values, not just "fail".
                self.assertIn("expected", output, f"{name}: {output}")
                self.assertIn("observed", output, f"{name}: {output}")
            else:
                self.assertIn("ALL PROOFS CHECK", output, f"{name}: {output}")


if __name__ == "__main__":
    unittest.main()
