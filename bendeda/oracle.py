# SPDX-License-Identifier: Apache-2.0
"""Sealed-oracle commit-reveal (issue #13, Phase 0.10).

The oracle is developed outside this repository and published as ciphertext plus
a commitment. Two commands, and the split is the point:

* `oracle seal` builds a deterministic archive, hashes every component, folds the
  hashes into one Merkle root, and records the root in `commitment.json`. The
  archive is encrypted; the plaintext never enters the repository.
* `oracle verify-commitment` recomputes the hashes and the root from a plaintext
  directory and compares. It needs **no decryption** and no key, because the
  commitment was built over the plaintext before encryption.

Determinism is load-bearing: a tar that embeds mtimes, user names or directory
iteration order produces a different root on every machine, and a commitment
nobody can reproduce is not a commitment. The archive is therefore written by
hand (sorted paths, zeroed metadata) rather than by `tar czf`.

Paths are sorted and hashed as UTF-8 POSIX-relative strings, so a seal made on
Windows and one made on Linux agree on the root.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

SCHEME = "bendeda-merkle-v1"
COMMITMENT_NAME = "commitment.json"
SUMS_NAME = "SHA256SUMS"
CANARY_NAME = "canary.txt"
RESULT_NAME = "oracle.json"
RESULT_SCHEME = "bendeda-oracle-result-v1"
SCORER_NAME = "score.py"
SCORER_TIMEOUT = 900
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NOTHING = 3

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


class OracleError(RuntimeError):
    """The oracle inputs cannot be sealed or verified as given."""


# --- components --------------------------------------------------------------


def collect(root: Path) -> list[str]:
    """Relative POSIX paths of every file under `root`, sorted.

    Sorting is part of the format: the Merkle root is defined over this order,
    and a different order would be a different commitment.
    """
    if not root.is_dir():
        raise OracleError(f"{root}: not a directory")
    found: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        found.append(relative.as_posix())
    return sorted(found)


def component_hashes(root: Path, components: Iterable[str] | None = None) -> dict[str, str]:
    names = sorted(components) if components is not None else collect(root)
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


def merkle_root(hashes: Mapping[str, str]) -> str:
    """One root over (path, digest) leaves; odd nodes are promoted, not duplicated.

    Duplicating the last node is the Bitcoin convention and it makes two
    different trees collide (a list and the same list with its last item doubled
    share a root). Promoting is simpler to explain and cannot do that.
    """
    if not hashes:
        raise OracleError("the Merkle root of no components is undefined")
    level = [
        hashlib.sha256(b"\x00" + name.encode("utf-8") + b"\x00" + digest.encode("ascii")).hexdigest()
        for name, digest in sorted(hashes.items())
    ]
    while len(level) > 1:
        paired: list[str] = []
        for index in range(0, len(level) - 1, 2):
            paired.append(
                hashlib.sha256(
                    b"\x01" + bytes.fromhex(level[index]) + bytes.fromhex(level[index + 1])
                ).hexdigest()
            )
        if len(level) % 2:
            paired.append(level[-1])
        level = paired
    return level[0]


# --- the archive -------------------------------------------------------------


def canonical_tar(root: Path, components: Sequence[str] | None = None) -> bytes:
    """A tar whose bytes depend only on the file names and contents."""
    names = list(components) if components is not None else collect(root)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name in names:
            if len(name.encode("utf-8")) > 100:
                raise OracleError(
                    f"{name}: the path is longer than USTAR allows (100 bytes); "
                    "shorten it rather than switching to a format with timestamps"
                )
            data = (root / name).read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.type = tarfile.REGTYPE
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


# --- the commitment ----------------------------------------------------------


@dataclass(frozen=True)
class Commitment:
    root: str
    components: Mapping[str, str]
    archive_sha256: str
    scheme: str = SCHEME

    def as_json(self) -> str:
        return (
            json.dumps(
                {
                    "scheme": self.scheme,
                    "root": self.root,
                    "archive_sha256": self.archive_sha256,
                    "leaf_count": len(self.components),
                    "components": dict(sorted(self.components.items())),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )


def build_commitment(root: Path) -> Commitment:
    components = component_hashes(root)
    if not components:
        raise OracleError(f"{root}: nothing to seal")
    archive = canonical_tar(root, sorted(components))
    return Commitment(
        root=merkle_root(components),
        components=components,
        archive_sha256=hashlib.sha256(archive).hexdigest(),
    )


def load_commitment(path: Path) -> Commitment:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("scheme") != SCHEME:
        raise OracleError(f"{path}: scheme is {raw.get('scheme')!r}, expected {SCHEME!r}")
    components = raw.get("components")
    if not isinstance(components, dict) or not components:
        raise OracleError(f"{path}: no components")
    return Commitment(
        root=str(raw["root"]),
        components={str(key): str(value) for key, value in components.items()},
        archive_sha256=str(raw.get("archive_sha256", "")),
    )


@dataclass
class Difference:
    name: str
    committed: str | None
    actual: str | None

    def render(self) -> str:
        if self.committed is None:
            return f"{self.name}: not in the commitment (added)"
        if self.actual is None:
            return f"{self.name}: committed as {self.committed[:12]}... but missing"
        return f"{self.name}: committed {self.committed[:12]}... but now {self.actual[:12]}..."


def compare(root: Path, commitment: Commitment) -> list[Difference]:
    actual = component_hashes(root)
    differences: list[Difference] = []
    for name in sorted(set(commitment.components) | set(actual)):
        committed = commitment.components.get(name)
        current = actual.get(name)
        if committed != current:
            differences.append(Difference(name, committed, current))
    return differences


# --- sealing -----------------------------------------------------------------


def _age(argv: Sequence[str], payload: bytes) -> tuple[int, str]:
    try:
        completed = subprocess.run(list(argv), input=payload, capture_output=True)
    except OSError as exc:
        return 3, f"could not run age: {exc}"
    return completed.returncode, (completed.stdout + completed.stderr).decode("utf-8", "replace")


def _age_argv(age: str | Sequence[str], recipient: str, target: Path) -> list[str]:
    base = [age] if isinstance(age, str) else list(age)
    return base + ["-r", recipient, "-o", str(target)]


def seal(
    root: Path,
    out: Path,
    recipient: str | None,
    age: str | Sequence[str] = "age",
    dry_run: bool = False,
) -> tuple[Commitment, Path | None]:
    """Seal `root` into `out`; returns the commitment and the ciphertext path.

    A plaintext archive is never written. If encryption cannot run, this raises
    rather than emitting a `.tar` that the absence guard would reject anyway.
    """
    commitment = build_commitment(root)
    if dry_run:
        return commitment, None
    if not recipient:
        raise OracleError("sealing needs a recipient (--recipient) for the age encryption")
    first = age if isinstance(age, str) else (age[0] if age else "")
    if not first or not (Path(first).exists() or shutil.which(first)):
        raise OracleError(f"age is not available ({first}); refusing to write a plaintext archive")
    archive = canonical_tar(root, sorted(commitment.components))
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{root.name}.tar.age"
    code, output = _age(_age_argv(age, recipient, target), archive)
    if code != 0:
        if target.exists():
            target.unlink()
        raise OracleError(f"age failed with status {code}: {output.strip()[:400]}")
    (out / COMMITMENT_NAME).write_text(commitment.as_json(), encoding="utf-8", newline="")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (out / SUMS_NAME).write_text(f"{digest}  {target.name}\n", encoding="utf-8", newline="")
    return commitment, target


# --- commands ----------------------------------------------------------------


def cmd_seal(args) -> int:
    root = Path(args.path)
    out = Path(args.out)
    try:
        commitment, target = seal(root, out, args.recipient, args.age, args.dry_run)
    except OracleError as exc:
        print(f"oracle seal: {exc}", file=sys.stderr)
        if args.dry_run:
            return EXIT_FAILED
        print("oracle seal: nothing was sealed (exit 3)", file=sys.stderr)
        return EXIT_NOTHING
    if args.json:
        print(commitment.as_json(), end="")
        return EXIT_OK
    print(f"oracle seal: {len(commitment.components)} component(s)")
    print(f"  merkle root    {commitment.root}")
    print(f"  archive sha256 {commitment.archive_sha256}")
    if target is None:
        print("  dry run: no archive and no commitment were written")
    else:
        print(f"  ciphertext     {target}")
        print(f"  commitment     {out / COMMITMENT_NAME}")
    return EXIT_OK


def record_result(
    bundle: Path,
    components: Mapping[str, bool],
    *,
    host: str,
    commitment: Path | None = None,
) -> Path:
    """Write `oracle.json` into a run bundle: the receiving end of the contract.

    `O` is the one verdict this repository cannot compute — the pack is scored on the
    scoring host (§5.4) — so the host has to hand back a result this code can check.
    It refuses a bundle that is void (an infrastructure failure has no oracle
    question), a bundle that scored `S=0` (zero is already the answer), and a bundle
    that already carries a result: a second score is a disagreement, not an update,
    and overwriting it would hide exactly the thing worth reading.
    """
    bundle = Path(bundle)
    target = bundle / RESULT_NAME
    if not (bundle / "events.jsonl").is_file():
        raise OracleError(f"{bundle}: not a run bundle (no events.jsonl)")
    if target.exists():
        raise OracleError(
            f"{target}: already carries an oracle result; a second one would hide the "
            "disagreement (move it aside to replace it)"
        )
    if not str(host).strip():
        raise OracleError("the scoring host must be named: an unattributed O is not evidence")
    if not components:
        raise OracleError("no components: an empty pack would make O vacuous")
    not_bool = sorted(str(name) for name, ok in components.items() if not isinstance(ok, bool))
    if not_bool:
        raise OracleError(f"components must be booleans; not: {', '.join(not_bool)}")

    from bendeda.score import load as load_bundle, score as score_events

    record = load_bundle(bundle)
    verdict = score_events(record.events, record.limits)
    if not verdict.scored:
        raise OracleError(f"{bundle}: {verdict.reason}; a void run has no O")
    if verdict.S == 0:
        raise OracleError(f"{bundle}: {verdict.reason}; S=0 already fixes O=0")

    payload: dict[str, object] = {
        "scheme": RESULT_SCHEME,
        "host": str(host).strip(),
        "components": {str(name): bool(ok) for name, ok in sorted(components.items())},
    }
    if commitment is not None:
        payload["commitment_root"] = load_commitment(Path(commitment)).root
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    return target


def cmd_record(args) -> int:
    bundle = Path(args.bundle)
    try:
        raw = json.loads(Path(args.components).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"oracle record: {exc}", file=sys.stderr)
        return EXIT_NOTHING
    components = raw.get("components") if isinstance(raw, dict) and "components" in raw else raw
    try:
        target = record_result(
            bundle,
            components if isinstance(components, dict) else {},
            host=args.host,
            commitment=Path(args.commitment) if args.commitment else None,
        )
    except (OracleError, ValueError) as exc:
        print(f"oracle record: {exc}", file=sys.stderr)
        print("oracle record: nothing was written (exit 3)", file=sys.stderr)
        return EXIT_NOTHING
    print(f"oracle record: {len(components)} component(s) from {args.host}")
    print(f"  {target}")
    return EXIT_OK


def pack_components(
    pack: Path,
    bundle: Path,
    *,
    timeout: float = SCORER_TIMEOUT,
    python: str | None = None,
) -> dict[str, bool]:
    """Run the pack's own scorer over a bundle and return its component verdicts.

    The pack is the thing that was sealed, so it has to answer for itself through a
    fixed entry point rather than the scoring host re-implementing it: `score.py` in
the pack root, called as `score.py <bundle>` with the pack as working directory,
    printing `{"components": {"name": true}}`. A missing entry point, a crash, a
    silence, output that is not JSON, or a result that is not an object is a
    refusal — never an empty set that `O` would read as vacuous.
    """
    # Absolute paths, because the scorer runs with the pack as its working directory:
    # a relative `score.py` would resolve against the pack and become pack/pack/score.py.
    script = (Path(pack) / SCORER_NAME).resolve()
    if not script.is_file():
        raise OracleError(f"{pack}: no {SCORER_NAME}; the pack has to score itself")
    try:
        completed = subprocess.run(
            [python or sys.executable, str(script), str(Path(bundle).resolve())],
            cwd=str(pack),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise OracleError(f"{pack}: the pack did not answer within {timeout:g}s") from None
    if completed.returncode != 0:
        lines = [line for line in completed.stderr.strip().splitlines() if line.strip()]
        raise OracleError(
            f"{pack}: the pack exited {completed.returncode}: "
            f"{lines[-1][:300] if lines else '(no output)'}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise OracleError(f"{pack}: the pack printed no JSON result ({exc})") from None
    if isinstance(payload, dict) and "components" in payload:
        payload = payload["components"]
    if not isinstance(payload, dict):
        raise OracleError(f"{pack}: the pack's result must be an object of name -> boolean")
    return payload


def cmd_oracle_score(args) -> int:
    """The scoring host's half: prove the pack is the sealed one, then let it score.

    Two failures are worth separating in the output. A pack that no longer matches the
    commitment is not the pack that was published, so scoring it would produce a
    number about different code; the differing files are named rather than counted.
    Everything after that — crash, timeout, bad JSON, non-boolean components, void
    bundle — is `oracle record`'s refusal, and nothing is written either way.
    """
    pack = Path(args.pack)
    bundle = Path(args.bundle)
    commitment_path = Path(args.commitment)
    try:
        commitment = load_commitment(commitment_path)
        differences = compare(pack, commitment)
    except (OSError, json.JSONDecodeError, KeyError, OracleError) as exc:
        print(f"oracle score: {exc}", file=sys.stderr)
        print("oracle score: nothing was scored (exit 3)", file=sys.stderr)
        return EXIT_NOTHING
    if differences:
        print(
            f"oracle score: the pack is not the sealed one: {len(differences)} file(s) "
            "differ from the commitment",
            file=sys.stderr,
        )
        for difference in differences:
            print(f"  {difference.render()}", file=sys.stderr)
        print(f"  committed root {commitment.root}", file=sys.stderr)
        print("oracle score: nothing was scored (exit 3)", file=sys.stderr)
        return EXIT_NOTHING
    try:
        components = pack_components(pack, bundle, timeout=args.timeout)
        target = record_result(bundle, components, host=args.host, commitment=commitment_path)
    except (OracleError, ValueError) as exc:
        print(f"oracle score: {exc}", file=sys.stderr)
        print("oracle score: nothing was written (exit 3)", file=sys.stderr)
        return EXIT_NOTHING
    print(f"oracle score: {len(components)} component(s) from {args.host}")
    print(f"  pack root {commitment.root}")
    print(f"  {target}")
    return EXIT_OK


def cmd_verify_commitment(args) -> int:
    root = Path(args.path)
    commitment_path = Path(args.commitment)
    if not root.is_dir():
        print(f"oracle verify-commitment: {root} is not a directory", file=sys.stderr)
        return EXIT_NOTHING
    if not commitment_path.exists():
        print(f"oracle verify-commitment: no commitment at {commitment_path}", file=sys.stderr)
        return EXIT_NOTHING
    try:
        commitment = load_commitment(commitment_path)
        differences = compare(root, commitment)
    except (OracleError, json.JSONDecodeError, KeyError) as exc:
        print(f"oracle verify-commitment: {exc}", file=sys.stderr)
        return EXIT_NOTHING

    if not differences:
        print(
            f"oracle verify-commitment: root matches ({len(commitment.components)} component(s))"
        )
        print(f"  {commitment.root}")
        return EXIT_OK

    print(
        f"oracle verify-commitment: {len(differences)} component(s) differ from the commitment",
        file=sys.stderr,
    )
    for difference in differences:
        print(f"  {difference.render()}", file=sys.stderr)
    recomputed = merkle_root(component_hashes(root))
    print(f"  committed root {commitment.root}", file=sys.stderr)
    print(f"  recomputed     {recomputed}", file=sys.stderr)
    return EXIT_FAILED
