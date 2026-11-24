# SPDX-License-Identifier: Apache-2.0
"""The per-run fingerprint (issue #6, Phase 0 exit criterion 2).

The daemon is faked here on purpose. The point of these tests is that a run
records the digest the daemon *resolved* and nothing it merely assumed: a tag is
not a digest, and the repository's pin file is not evidence about what ran.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from bendeda.canary.runner import Checker
from bendeda.provenance import environment, image_identity

IMAGE = "bendeda/bend:2.0.40"
DIGEST = "sha256:3f1c2a9d8e7b6a5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c"


def fake_run(digest: str = DIGEST, version: str = "Bend 2.0.40") -> object:
    calls: list[list[str]] = []

    def run(argv):
        calls.append(list(argv))
        if argv[1] == "image":
            return 0, digest
        return 0, version

    run.calls = calls  # type: ignore[attr-defined]
    return run


class TestImageIdentity(unittest.TestCase):
    def test_the_digest_and_version_are_what_the_daemon_reports(self) -> None:
        run = fake_run()
        facts = image_identity("docker", IMAGE, run)  # type: ignore[arg-type]
        self.assertEqual(facts["image"], IMAGE)
        self.assertEqual(facts["image_id"], DIGEST)
        self.assertEqual(facts["bend_version"], "Bend 2.0.40")
        self.assertEqual(
            run.calls,  # type: ignore[attr-defined]
            [
                ["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE],
                ["docker", "run", "--rm", IMAGE, "version"],
            ],
        )

    def test_a_missing_image_is_recorded_as_a_missing_image(self) -> None:
        facts = image_identity(
            "docker", IMAGE, lambda argv: (1, "Error: No such image: bendeda/bend:2.0.40")
        )
        self.assertNotIn("image_id", facts)
        self.assertIn("No such image", facts["image_id_missing"])
        self.assertNotIn("bend_version", facts)
        self.assertIn("bend_version_missing", facts)

    def test_a_tag_is_not_accepted_as_a_digest(self) -> None:
        facts = image_identity("docker", IMAGE, lambda argv: (0, IMAGE))
        self.assertNotIn("image_id", facts)


class TestEnvironment(unittest.TestCase):
    def test_an_image_checker_records_the_image_it_ran(self) -> None:
        checker = Checker(
            ["docker", "run", "--rm", "-v", ".", "-w", "/work", IMAGE],
            Path("."),
            IMAGE,
            image=IMAGE,
        )
        facts = environment(checker, "docker", fake_run())  # type: ignore[arg-type]
        self.assertEqual(facts["image_id"], DIGEST)
        self.assertEqual(facts["bend_version"], "Bend 2.0.40")
        self.assertEqual(facts["checker"], IMAGE)

    def test_a_local_checker_says_there_is_no_image(self) -> None:
        checker = Checker(["bun", ".bend-cache/bend2/main.ts"], Path("."), "bun main.ts")
        facts = environment(checker, "docker", fake_run())  # type: ignore[arg-type]
        self.assertNotIn("image_id", facts)
        self.assertIn("none", facts["image"])
        self.assertNotIn("bend_version", facts)


if __name__ == "__main__":
    unittest.main()
