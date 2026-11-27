# SPDX-License-Identifier: Apache-2.0
"""The B1 FIFO task package (issue #14, draft).

The package keeps laws and proofs in separate files, because the harness gives
the agent the laws and hides the reference proofs, and because `law mutate`
inlines the model rather than importing it. Nothing in the repository composes
the three files, so the composition lives here: a package whose proofs were never
composed is a claim, not evidence.

Tested properties:

* composed model + LAWS + PROOF_ref checks under the pinned compiler;
* the negative control is refused, with both values printed;
* `law lint` finds nothing on the package, which is only meaningful because a
  seeded fixture elsewhere proves the rules fire when they should;
* the manifest and the law file describe the same set of laws, every witness it
  names exists, every requirement is covered or explicitly exempt, and every
  translated law names an assertion or cover that is in `props_locked.sv`.
"""

from __future__ import annotations

import re

import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from bendeda.laws import run
from bendeda.laws.manifest import Manifest
from bendeda.laws.source import parse

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "tasks" / "seq" / "B1_fifo"
NL = chr(10)


def bend_command() -> list[str] | None:
    bun = os.environ.get("BENDEDA_BUN")
    cli = os.environ.get("BENDEDA_BEND_CLI")
    if bun and cli and Path(cli).exists():
        return [bun, cli]
    found = shutil.which("bend")
    return [found] if found else None


def compose(*names: str) -> str:
    return NL.join((TASK / name).read_text(encoding="utf-8").rstrip(NL) for name in names) + NL


class TestPackageFiles(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = Manifest.load(TASK / "laws.manifest.yaml")
        self.laws = parse((TASK / "LAWS.bend").read_text(encoding="utf-8"), TASK / "LAWS.bend")

    def test_the_law_file_and_the_manifest_describe_the_same_laws(self) -> None:
        self.assertEqual(self.laws.problems, [])
        self.assertEqual(
            {law.name for law in self.laws.laws},
            set(self.manifest.by_name),
        )
        self.assertEqual(len(self.manifest.laws), 22)

    def test_every_manifest_id_matches_its_law_name_prefix(self) -> None:
        for entry in self.manifest.laws:
            prefix = "fifo_" + entry.id.split("-")[1].lower() + entry.id.split("-")[2] + "_"
            self.assertTrue(entry.name.startswith(prefix), f"{entry.id}: {entry.name}")

    def test_every_witness_named_by_the_manifest_is_a_law(self) -> None:
        names = {law.name for law in self.laws.laws}
        witnesses = {entry.witness for entry in self.manifest.laws if entry.witness}
        self.assertTrue(witnesses)
        self.assertLessEqual(witnesses, names)

    def test_every_requirement_is_covered_or_declared_exempt(self) -> None:
        covered = {req for entry in self.manifest.laws for req in entry.requirements}
        exempt = set(self.manifest.conformance_only) | set(self.manifest.oracle_only)
        declared = set(self.manifest.requirements or ())
        self.assertEqual(covered | exempt, declared)

    def test_the_specification_states_every_declared_requirement(self) -> None:
        spec = (TASK / "spec.md").read_text(encoding="utf-8")
        for requirement in self.manifest.requirements or ():
            self.assertIn(f"| {requirement} |", spec, requirement)

    def test_every_translated_law_names_a_property_that_exists(self) -> None:
        props = (TASK / "props_locked.sv").read_text(encoding="utf-8")
        for entry in self.manifest.laws:
            translation = entry.translation or {}
            if translation.get("sva"):
                name = translation["sva"]
                # The pack is labelled immediate assertions, not named `property`
                # blocks: the pinned Yosys front end rejects those. The label is what
                # the manifest and L011 name, so that is what has to exist.
                self.assertRegex(
                    props,
                    rf"(?m)^\s*{re.escape(name)}:\s*(assert|cover)\b",
                    entry.name,
                )

    def test_no_escape_hatch_appears_in_the_law_or_model_files(self) -> None:
        findings = [f.render() for f in run([str(TASK)]).findings]
        self.assertEqual(findings, [])

    def test_the_model_offers_la3_at_least_twenty_mutants(self) -> None:
        # LA3 pre-registers 20. The model is a transition table, so this only
        # holds because the catalogue mutates branches as well as arithmetic.
        from bendeda.laws.mutate import candidates

        model = (TASK / "model.bend").read_text(encoding="utf-8")
        self.assertGreaterEqual(len(candidates(model)), 20)


class TestPackageChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.command = bend_command()
        if self.command is None:
            self.skipTest(
                "no Bend compiler: set BENDEDA_BUN and BENDEDA_BEND_CLI, or put bend on PATH"
            )
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def gate(self, text: str) -> str:
        path = Path(self.tmp.name) / "book.bend"
        path.write_text(text, encoding="utf-8", newline="")
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

    def test_the_reference_proofs_close_every_law(self) -> None:
        output = self.gate(compose("model.bend", "LAWS.bend", "PROOF_ref.bend"))
        self.assertIn("ALL PROOFS CHECK", output, output)

    def test_the_negative_control_is_refused_with_both_values(self) -> None:
        output = self.gate(
            compose("model.bend", "negative/fifo_n01_strict_below_depth.bend")
        )
        self.assertIn("SOME PROOFS FAIL", output, output)
        self.assertNotIn("ALL PROOFS CHECK", output)
        self.assertIn("expected", output)
        self.assertIn("observed", output)


if __name__ == "__main__":
    unittest.main()
