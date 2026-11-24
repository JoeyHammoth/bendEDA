# SPDX-License-Identifier: Apache-2.0
"""What a run has to name to be reproducible: its image digest and tool version.

Phase 0 exit criterion 2 (issue #6) says every run records the image digest and
`bend version` it used. A tag is not that: `bendeda/bend:2.0.40` can be rebuilt,
and two images with the same tag are different images. The digest is read from
the daemon that will actually run the checker, so a missing image is reported as
an absence rather than papered over with the tag or the repository's pin file.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from typing import Callable, Sequence

#: Same shape as `bendeda.canary.runner.run_argv`, narrowed to argv only, so a
#: test can answer without a daemon.
Runner = Callable[[Sequence[str]], tuple[int, str]]


def _run(argv: Sequence[str]) -> tuple[int, str]:
    argv = list(argv)
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        return completed.returncode, (completed.stdout + completed.stderr).strip()
    except OSError:
        # Docker Desktop on Windows is often off PATH and named by a POSIX path,
        # which CreateProcess cannot start. Same shim as the checker runner, so a
        # gate that can run can also record what it ran.
        shell = " ".join(shlex.quote(part) for part in argv)
        try:
            completed = subprocess.run(
                ["bash", "-c", shell],
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "MSYS2_ARG_CONV_EXCL": "*"},
            )
            return completed.returncode, (completed.stdout + completed.stderr).strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 127, str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, f"the daemon did not answer within 120 s: {exc}"


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:200]
    return ""


def image_identity(docker: str, image: str, run: Runner = _run) -> dict[str, str]:
    """The digest the daemon resolved, and the version the image reports itself."""
    facts: dict[str, str] = {"image": image}
    code, output = run([docker, "image", "inspect", "--format", "{{.Id}}", image])
    resolved = _first_line(output)
    if code == 0 and resolved.startswith("sha256:"):
        facts["image_id"] = resolved
    else:
        facts["image_id_missing"] = resolved or "no output"
    code, output = run([docker, "run", "--rm", image, "version"])
    reported = _first_line(output)
    if code == 0 and reported:
        facts["bend_version"] = reported
    else:
        facts["bend_version_missing"] = reported or "no output"
    return facts


def environment(checker, docker: str = "docker", run: Runner = _run) -> dict[str, str]:
    """The fingerprint of the checker a gate ran against.

    Local mode has no image to name, and it says so: the compiler is the pinned
    source tree under Bun, whose identity is the recorded source digests, not a
    release binary.
    """
    facts: dict[str, str] = {"checker": checker.label, "mode": checker.mode}
    image = getattr(checker, "image", None)
    if image:
        facts.update(image_identity(docker, image, run))
    else:
        facts["image"] = "none (local source pin)"
    return facts
