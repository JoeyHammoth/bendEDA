# SPDX-License-Identifier: Apache-2.0
"""The agent runner: one mount, one network, one proxy (issue #15).

`plan` prints the commands, `up` runs them in the order that makes the proxy the only
egress (network, then proxy, then agent, each step gated on the previous answering),
`down` removes them, and `check` refutes a live container afterwards. Every failure
path in `up` tears down what it started, because a half-built sandbox is worse than
none: the agent would exist without the proxy that governs it.

What the checks buy is the property the issue asks for, stated as something a machine
can refute: the agent container is attached to exactly one network, that network has
no gateway, the only bind mount is the workspace, and the oracle is not reachable
through any mount.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

DEFAULT_IMAGE = "bendeda/harness:0.0.1"
DEFAULT_NETWORK = "bendeda-offline"
PROXY_NAME = "bendeda-policy-proxy"
AGENT_NAME = "bendeda-agent"
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
    return [network, proxy, agent_command(spec)]


def agent_command(spec: AgentSpec, keepalive: bool = False) -> list[str]:
    """The agent's argv. `keepalive` starts a container to be driven later."""
    workspace = Path(_docker_path(spec.workspace))
    argv = [
        "docker", "run", "--rm", "--name", AGENT_NAME, "--network", spec.network,
        # Exactly one mount: the workspace. The oracle is not among them, which is the
        # whole point, so it is nowhere in this argv.
        "--mount", f"type=bind,source={_docker_path(workspace)},target=/work",
        "--env", f"BENDEDA_PROXY=http://{PROXY_NAME}:{PROXY_PORT}",
        "--workdir", "/work",
    ]
    if keepalive:
        # `up` returns once the sandbox exists; the task arrives through `docker
        # exec`, so the container must not exit the moment it starts. Detached, or
        # the CLI blocks for the life of the container — which is how the first run
        # of `up` sat in `subprocess.run` until its timeout fired.
        return argv + ["-d", "--entrypoint", "sleep", spec.image, "infinity"]
    return argv + ["--entrypoint", "python", spec.image, "-m", "bendeda", *spec.command]


class SandboxError(RuntimeError):
    """Starting the sandbox failed; whatever started has already been removed."""


def _last(output: str) -> str:
    lines = [line.strip() for line in output.strip().splitlines() if line.strip()]
    return lines[-1] if lines else "(no output)"


def _wait_for_proxy(spec: AgentSpec, run=None, attempts: int = 20, pause: float = 0.5) -> bool:
    """The proxy answers before the agent is allowed to exist."""
    run = run or _run
    probe = [
        "docker", "exec", PROXY_NAME, "python", "-c",
        f"import urllib.request as u; u.urlopen('http://127.0.0.1:{PROXY_PORT}/health', timeout=2)",
    ]
    for _ in range(attempts):
        code, _output = run(probe)
        if code == 0:
            return True
        time.sleep(pause)
    return False


def up(spec: AgentSpec, run=None, wait=None) -> list[str]:
    """Start network, proxy and agent — or leave nothing behind trying.

    Order carries the guarantee: the network exists before the proxy is attached to
    it, and the proxy answers before the agent exists at all. Every failure runs the
    teardown first, because an agent without its proxy is the one outcome worse than
    no sandbox.
    """
    run = run or _run
    network, proxy, _agent = plan(spec)
    wait = wait or _wait_for_proxy
    started: list[str] = []
    for name, argv in (
        ("network", network),
        ("proxy", proxy),
        ("agent", agent_command(spec, keepalive=True)),
    ):
        code, output = run(argv)
        if code != 0:
            down(spec, run)
            raise SandboxError(f"{name} did not start: {_last(output)}")
        started.append(name)
    if not wait(spec, run):
        down(spec, run)
        raise SandboxError(f"the proxy never answered on port {PROXY_PORT}; the sandbox was removed")
    return started


def down(spec: AgentSpec, run=None) -> list[str]:
    """Remove the containers and the network. Something already gone is not a problem."""
    run = run or _run
    problems: list[str] = []
    for name in (AGENT_NAME, PROXY_NAME):
        code, output = run(["docker", "rm", "-f", name])
        if code != 0 and "no such" not in output.lower():
            problems.append(f"could not remove {name}: {_last(output)}")
    code, output = run(["docker", "network", "rm", spec.network])
    if code != 0 and "not found" not in output.lower():
        problems.append(f"could not remove network {spec.network}: {_last(output)}")
    return problems


def _run(argv: Sequence[str]) -> tuple[int, str]:
    argv = list(argv)
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        return completed.returncode, completed.stdout + completed.stderr
    except subprocess.TimeoutExpired:
        # A command that never returns is a failed step, not an exception the caller
        # has to know about: `up` needs a return code so it can tear the sandbox down.
        return 1, f"{argv[0]} {argv[1] if len(argv) > 1 else ''} timed out after 120s"
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


def exec_in(container: str, argv: Sequence[str], run=None) -> tuple[int, str]:
    """Run the arm's work inside the sandbox, where the proxy governs it.

    `up` starts a keepalive container precisely so the scored command runs here and
    not on the host: a command run outside the container is not the run the log
    describes.
    """
    run = run or _run
    return run(["docker", "exec", container, *argv])


def submit(container: str, resource: str, run=None) -> tuple[int, str]:
    """Record a submission by calling the proxy from inside the agent's network.

    The host can reach neither the internal network nor the agent, so the submit
    event has to be posted from the container — which is also what keeps the proxy
    the only thing that writes the log.
    """
    run = run or _run
    script = (
        "import json, sys, urllib.error as e, urllib.request as u\n"
        "try:\n"
        f"    r = u.urlopen(u.Request('http://{PROXY_NAME}:{PROXY_PORT}/call', data=json.dumps("
        f"{{'tool': 'submit', 'resource': {resource!r}}}).encode(), "
        "headers={'Content-Type': 'application/json'}), timeout=10)\n"
        "    print(r.status)\n"
        "except e.HTTPError as exc:\n"
        "    print('refused', exc.code)\n"
        "    sys.exit(1)\n"
    )
    return run(["docker", "exec", container, "python", "-c", script])


def mount_target(source: str) -> str:
    """Where a mount source lands inside the container, for reporting."""
    return posixpath.normpath(source)
