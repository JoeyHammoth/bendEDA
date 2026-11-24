# SPDX-License-Identifier: Apache-2.0
"""The agent runner: one mount, one network, one proxy (issue #15).

The runner is a specification plus two checks. It does *not* start containers yet —
that is the next step and it is obvious when it happens, because `plan` writes to
stdout only.

What the checks buy today is the property the issue asks for, stated as something a
machine can refute: the agent container is attached to exactly one network, that
network has no gateway, the only bind mount is the workspace, and the oracle is not
reachable through any mount.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

DEFAULT_IMAGE = "bendeda/harness:0.0.1"
DEFAULT_NETWORK = "bendeda-offline"
PROXY_NAME = "bendeda-policy-proxy"
PROXY_PORT = 8765


@dataclass(frozen=True)
class AgentSpec:
    workspace: Path
    image: str = DEFAULT_IMAGE
    network: str = DEFAULT_NETWORK
    policy: Path | None = None
    events: Path | None = None
    command: tuple[str, ...] = ("--version",)


class Unrunnable(ValueError):
    """The specification cannot produce a sandbox, so it must not be planned."""


_MSYS_DRIVE = re.compile(r"^/([A-Za-z])/")


def _docker_path(path: Path | str) -> str:
    """An absolute path in the form the daemon expects, from either shell form.

    Git Bash hands out `/c/Users/...`, which Windows resolves to `C:\\c\\Users\\...`;
    the drive prefix has to be converted before resolving or the comparison invents
    a mount that is not there. On Linux `/c/x` is a real path and stays as it is.
    """
    text = str(path).replace("\\", "/")
    if os.name == "nt":
        match = _MSYS_DRIVE.match(text)
        if match:
            text = f"{match.group(1).upper()}:/" + text[3:]
    return str(Path(text).resolve()).replace("\\", "/")


def _normalise_source(text: str) -> str:
    """One form for a bind source, whatever the daemon reports.

    Docker Desktop on Windows reports `C:/Users/...` on one call and `/c/Users/...`
    on another, so a raw string comparison invents a problem that is not there.
    """
    text = text.replace("\\", "/")
    match = _MSYS_DRIVE.match(text)
    if match:
        text = f"{match.group(1).upper()}:/" + text[3:]
    return text.rstrip("/").lower()


def plan(spec: AgentSpec) -> list[list[str]]:
    """The commands that would create the sandbox, or raise `Unrunnable`."""
    workspace = Path(_docker_path(spec.workspace))
    if not workspace.is_dir():
        raise Unrunnable(f"workspace is not a directory: {workspace}")
    if spec.policy is None or spec.events is None:
        raise Unrunnable("a proxy policy and an event log are required: the proxy is the only egress")

    network = ["docker", "network", "create", "--internal", spec.network]
    proxy = [
        "docker", "run", "-d", "--name", PROXY_NAME, "--network", spec.network,
        "--mount", f"type=bind,source={_docker_path(spec.policy)},target=/policy.json,readonly",
        "--mount", f"type=bind,source={_docker_path(spec.events.parent)},target=/events",
        "--entrypoint", "python", spec.image,
        "-m", "bendeda", "proxy", "serve",
        "--policy", "/policy.json", "--events", f"/events/{spec.events.name}",
        "--host", "0.0.0.0", "--port", str(PROXY_PORT),
    ]
    agent = [
        "docker", "run", "--rm", "--name", "bendeda-agent", "--network", spec.network,
        # Exactly one mount: the workspace. The oracle is not among them, which is the
        # whole point, so it is nowhere in this argv.
        "--mount", f"type=bind,source={_docker_path(workspace)},target=/work",
        "--env", f"BENDEDA_PROXY=http://{PROXY_NAME}:{PROXY_PORT}",
        "--workdir", "/work",
        "--entrypoint", "python", spec.image, "-m", "bendeda", *spec.command,
    ]
    return [network, proxy, agent]


def _run(argv: Sequence[str]) -> tuple[int, str]:
    argv = list(argv)
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        return completed.returncode, completed.stdout + completed.stderr
    except OSError:
        shell = " ".join(shlex.quote(part) for part in argv)
        completed = subprocess.run(
            ["bash", "-c", shell],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "MSYS2_ARG_CONV_EXCL": "*"},
        )
        return completed.returncode, completed.stdout + completed.stderr


def _load(text: str) -> dict:
    data = json.loads(text)
    return data[0] if isinstance(data, list) else data


def check(
    container: str,
    network: str,
    workspace: Path,
    oracle: Path | None = None,
    run=_run,
) -> list[str]:
    """Problems that would make this container an unmanaged agent. Empty means clean."""
    problems: list[str] = []
    code, output = run(["docker", "inspect", container])
    if code != 0:
        return [f"cannot inspect {container}: {output.strip().splitlines()[-1] if output.strip() else code}"]
    try:
        body = _load(output)
    except json.JSONDecodeError as exc:
        return [f"docker inspect did not return JSON: {exc}"]

    attached = set((body.get("NetworkSettings") or {}).get("Networks") or {})
    if attached != {network}:
        problems.append(f"attached to {sorted(attached)}, expected only {network}")
    if "host" in attached:
        problems.append("attached to host networking")

    mounts = body.get("Mounts") or []
    sources = [_normalise_source(str(m.get("Source", ""))) for m in mounts if m.get("Source")]
    expected = _normalise_source(_docker_path(workspace))
    if sources != [expected]:
        problems.append(f"mounts are {sources}, expected exactly [{expected}]")
    if oracle is not None:
        target = _normalise_source(_docker_path(oracle))
        for source in sources:
            if source == target or target.startswith(source.rstrip("/") + "/"):
                problems.append(f"the oracle is reachable through the mount {source}")

    code, output = run(["docker", "network", "inspect", network])
    if code != 0:
        problems.append(f"cannot inspect network {network}")
        return problems
    try:
        net = _load(output)
    except json.JSONDecodeError as exc:
        return problems + [f"docker network inspect did not return JSON: {exc}"]
    if not net.get("Internal"):
        problems.append(f"network {network} is not internal, so it has a route off the machine")
    return problems


def mount_target(source: str) -> str:
    """Where a mount source lands inside the container, for reporting."""
    return posixpath.normpath(source)
