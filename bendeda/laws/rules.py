# SPDX-License-Identifier: Apache-2.0
"""Rules L001-L015 over one task package (Appendix G.11).

Each rule is a function of the package and appends `Finding`s. They are
separate functions so a test can seed one defect and assert the rule that was
supposed to see it, rather than asserting a count.

Two properties matter and are stated here because they are easy to lose:

* No rule is silent about its own blindness. A rule that needs metadata the
  package does not carry (the requirement list for L004, a mutation report for
  L006) appends a note saying it was not evaluated. A clean report then means
  "every applicable rule ran", not "no rule had anything to say".
* A rule fires on the defect, not on the neighbourhood. The naming rule (L008)
  compares the manifest id to the manifest name; the traceability rule (L003)
  is separate from missing priority (L012), so a package with one defect does
  not produce five findings that all point at it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from bendeda.laws.base_symbols import BASE_SYMBOLS
from bendeda.laws.manifest import Manifest, read as read_yaml
from bendeda.laws.source import BendFile, Law, parse as parse_bend

RULES: dict[str, str] = {
    "L001": "a conditional law has no witness",
    "L002": "a law is in the file but not the manifest, or the reverse",
    "L003": "a law maps to no requirement",
    "L004": "a requirement has no law and is not declared conformance- or oracle-only",
    "L005": "a law's hypothesis is unsatisfiable as written",
    "L006": "a law survived every model mutant (no mutation report: not evaluated)",
    "L007": "an escape-hatch construct appears in a law or model file",
    "L008": "a law name does not follow the id convention",
    "L009": "two laws are duplicate or alpha-equivalent",
    "L010": "a law references a symbol outside the package and Base",
    "L011": "a transferable law has no translation and no declared reason",
    "L012": "a law has no priority tier",
    "L013": "a law conjoins more than one claim",
    "L014": "a declared artifact hash does not match the file",
    "L015": "the provenance sidecar is absent or its hashes do not match",
}

NEGATIVE_CLASS = "L-NEG"
CONDITIONAL_CLASSES = {"L-FUNC", "L-REFN"}
TRANSFERABLE_CLASSES = {"L-SAFE", "L-FUNC", "L-REFN"}
PRIORITIES = {"core", "important", "extended"}

#: Bend 2.0.40 constructs that bypass the checker. This is the Phase 0 subset;
#: the full enumerated list is issue #11 and this tuple is where it lands.
ESCAPE_HATCHES: tuple[tuple[str, str], ...] = (
    (r"@unsafe\b", "@unsafe"),
    (r"\bdef\s+[A-Za-z_][\w.]*\?\s*\(", "a def whose name ends in '?' (unchecked)"),
    (r"\?TODO\b", "?TODO (a goal left open)"),
    (r"\bTODO\b", "TODO in a checked file"),
)

KNOWN_NAMESPACES = {
    "Bool", "Cmp", "Nat", "Word", "U32", "U64", "F32", "IO", "List", "Map",
    "String", "Equal", "Empty", "Maybe", "Result", "Pair", "Type",
}

_ID = re.compile(r"^([A-Za-z0-9]+)-([A-Z])-(\d{2})$")
_CALL = re.compile(r"\b([A-Z][A-Za-z0-9_]*\.[a-z][A-Za-z0-9_]*)\b")
_LITERAL = re.compile(r"^(?:True\{\}|False\{\}|WNil\{\}|Nil\{\}|-?\d+n?)$")


@dataclass(frozen=True)
class Finding:
    rule: str
    message: str
    law: str | None = None
    path: str | None = None
    line: int | None = None

    def render(self) -> str:
        where = self.path or ""
        if self.line is not None:
            where = f"{where}:{self.line}" if where else f"line {self.line}"
        target = f" [{self.law}]" if self.law else ""
        return f"{self.rule} {where}{target}: {self.message}"

    def as_json(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "message": self.message,
            "law": self.law,
            "path": self.path,
            "line": self.line,
        }


@dataclass
class Package:
    root: Path
    manifest: Manifest
    laws: BendFile
    model: BendFile | None = None
    bv: BendFile | None = None
    provenance: Mapping[str, Any] | None = None
    provenance_error: str | None = None
    mutation: Mapping[str, Any] | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def local_names(self) -> set[str]:
        names = set(self.laws.law_names()) | {d.name for d in self.laws.defs}
        for extra in (self.model, self.bv):
            if extra is not None:
                names |= extra.law_names() | {d.name for d in extra.defs}
        return names


def _rel(package: Package, path: Path) -> str:
    try:
        return path.relative_to(package.root).as_posix()
    except ValueError:
        return path.name


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- L001 -------------------------------------------------------------------


def l001_witness(package: Package, out: list[Finding]) -> None:
    entries = package.manifest.by_name
    for law in package.laws.laws:
        entry = entries.get(law.name)
        if entry is None:
            continue
        conditional = law.conditional or entry.law_class in CONDITIONAL_CLASSES
        if conditional and not (entry.witness or "").strip():
            out.append(
                Finding(
                    "L001",
                    "conditional law has no witness: nothing shows the hypothesis is reachable",
                    law.name,
                    _rel(package, package.laws.path) if package.laws.path else None,
                    law.line,
                )
            )


# --- L002 -------------------------------------------------------------------


def l002_presence(package: Package, out: list[Finding]) -> None:
    in_file = {law.name: law for law in package.laws.laws}
    in_manifest = package.manifest.by_name
    laws_path = _rel(package, package.laws.path) if package.laws.path else None
    for name, law in in_file.items():
        if name not in in_manifest:
            out.append(
                Finding("L002", "law is in the file but has no manifest entry", name, laws_path, law.line)
            )
    for name in in_manifest:
        if name not in in_file:
            out.append(
                Finding(
                    "L002",
                    "manifest entry has no law in the file",
                    name,
                    _rel(package, package.manifest.path),
                )
            )


# --- L003 -------------------------------------------------------------------


def l003_traceability(package: Package, out: list[Finding]) -> None:
    for entry in package.manifest.laws:
        if entry.is_negative_control:
            continue
        if not entry.requirements:
            out.append(
                Finding(
                    "L003",
                    "law maps to no requirement",
                    entry.name,
                    _rel(package, package.manifest.path),
                )
            )


# --- L004 -------------------------------------------------------------------


def l004_coverage(package: Package, out: list[Finding]) -> None:
    declared = package.manifest.requirements
    if declared is None:
        package.notes.append(
            "L004 not evaluated: the manifest declares no `requirements` list, "
            "so there is nothing to compare law coverage against"
        )
        return
    covered = {req for entry in package.manifest.laws for req in entry.requirements}
    exempt = set(package.manifest.conformance_only) | set(package.manifest.oracle_only)
    for requirement in declared:
        if requirement not in covered and requirement not in exempt:
            out.append(
                Finding(
                    "L004",
                    f"requirement {requirement} has no law and is not declared "
                    "conformance-only or oracle-only",
                    None,
                    _rel(package, package.manifest.path),
                )
            )


# --- L005 -------------------------------------------------------------------


def _unsatisfiable(hypothesis: str) -> bool:
    text = hypothesis.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return False
    inner = text[1:-1]
    sides = inner.rsplit(":", 1)[0]
    if "==" not in sides:
        return False
    left, right = sides.split("==", 1)
    left, right = left.strip(), right.strip()
    if not _LITERAL.match(left) or not _LITERAL.match(right):
        return False
    return left != right


def l005_hypothesis(package: Package, out: list[Finding]) -> None:
    laws_path = _rel(package, package.laws.path) if package.laws.path else None
    for law in package.laws.laws:
        for param in law.params:
            if param.hypothesis and _unsatisfiable(param.type):
                out.append(
                    Finding(
                        "L005",
                        f"hypothesis `{param.type}` is a false closed equation: "
                        "the law holds vacuously",
                        law.name,
                        laws_path,
                        law.line,
                    )
                )


# --- L006 -------------------------------------------------------------------


def l006_mutation(package: Package, out: list[Finding]) -> None:
    if package.mutation is None:
        package.notes.append(
            "L006 not evaluated: no mutation report was supplied "
            "(`bendeda law mutate ... --out <file>` then `law lint --mutation <file>`)"
        )
        return
    laws = package.mutation.get("laws")
    if not isinstance(laws, dict):
        package.notes.append("L006 not evaluated: the mutation report has no `laws` map")
        return
    for name, record in laws.items():
        if not isinstance(record, dict):
            continue
        killed_by = record.get("killed_by")
        total = record.get("total")
        if killed_by == 0:
            out.append(
                Finding(
                    "L006",
                    f"law survived all {total if total is not None else 'the'} model mutants, "
                    "so it does not constrain the model",
                    str(name),
                    None,
                )
            )


# --- L007 -------------------------------------------------------------------


def l007_escape_hatches(package: Package, out: list[Finding]) -> None:
    for bend_file in (package.laws, package.model, package.bv):
        if bend_file is None:
            continue
        for number, line in enumerate(bend_file.text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            for pattern, description in ESCAPE_HATCHES:
                if re.search(pattern, line):
                    out.append(
                        Finding(
                            "L007",
                            f"escape hatch: {description}",
                            None,
                            _rel(package, bend_file.path) if bend_file.path else None,
                            number,
                        )
                    )


# --- L008 -------------------------------------------------------------------


def expected_name(task: str, law_id: str) -> str | None:
    """The identifier convention from G-18: `<task>_<class letter><nn>_<slug>`."""
    match = _ID.match(law_id)
    if match is None:
        return None
    _, letter, number = match.groups()
    task_slug = task.split("_")[-1].lower()
    return f"{task_slug}_{letter.lower()}{number}_"


def l008_naming(package: Package, out: list[Finding]) -> None:
    manifest_rel = _rel(package, package.manifest.path)
    laws_rel = _rel(package, package.laws.path) if package.laws.path else None
    for entry in package.manifest.laws:
        prefix = expected_name(package.manifest.task, entry.id)
        if prefix is None:
            out.append(
                Finding(
                    "L008",
                    f"id `{entry.id}` does not follow `<TASK>-<class letter>-<nn>`",
                    entry.name,
                    manifest_rel,
                )
            )
            continue
        if not re.match(rf"^{re.escape(prefix)}[a-z0-9_]+$", entry.name):
            out.append(
                Finding(
                    "L008",
                    f"name `{entry.name}` does not follow `{prefix}<slug>`",
                    entry.name,
                    manifest_rel,
                )
            )
    by_name = package.manifest.by_name
    for law in package.laws.laws:
        entry = by_name.get(law.name)
        if entry is not None and entry.name != law.name:
            out.append(
                Finding("L008", "the law's name differs from the manifest name", law.name, laws_rel, law.line)
            )


# --- L009 -------------------------------------------------------------------


def alpha_key(law: Law) -> str:
    """The claim with each parameter replaced by its position.

    This is alpha-equivalence at the syntactic level: renaming a law's
    parameters does not make it a different law, and a checker would not
    notice either.
    """
    text = " ".join(law.claim.split())
    for position, param in enumerate(law.params):
        text = re.sub(rf"\b{re.escape(param.name)}\b", f"p{position}", text)
    return text


def l009_duplicates(package: Package, out: list[Finding]) -> None:
    laws_rel = _rel(package, package.laws.path) if package.laws.path else None
    seen: dict[str, Law] = {}
    for law in package.laws.laws:
        if not law.claim:
            continue
        key = alpha_key(law)
        first = seen.get(key)
        if first is None:
            seen[key] = law
            continue
        out.append(
            Finding(
                "L009",
                f"alpha-equivalent to `{first.name}` (line {first.line})",
                law.name,
                laws_rel,
                law.line,
            )
        )


# --- L010 -------------------------------------------------------------------


def l010_symbols(package: Package, out: list[Finding]) -> None:
    allowed_local = package.local_names
    laws_rel = _rel(package, package.laws.path) if package.laws.path else None
    for law in package.laws.laws:
        for symbol in _CALL.findall(law.claim):
            if symbol in allowed_local or symbol in BASE_SYMBOLS:
                continue
            out.append(
                Finding(
                    "L010",
                    f"`{symbol}` is not defined in the package, Base, or the abstraction map",
                    law.name,
                    laws_rel,
                    law.line,
                )
            )


# --- L011 -------------------------------------------------------------------


def l011_translation(package: Package, out: list[Finding]) -> None:
    for entry in package.manifest.laws:
        if entry.law_class not in TRANSFERABLE_CLASSES:
            continue
        translation = entry.translation or {}
        reason = entry.raw.get("translation_reason")
        if translation.get("sva") or (isinstance(reason, str) and reason.strip()):
            continue
        out.append(
            Finding(
                "L011",
                f"class {entry.law_class} needs a translation or a declared reason it is model-level",
                entry.name,
                _rel(package, package.manifest.path),
            )
        )


# --- L012 -------------------------------------------------------------------


def l012_priority(package: Package, out: list[Finding]) -> None:
    for entry in package.manifest.laws:
        if entry.is_negative_control:
            continue
        if entry.priority not in PRIORITIES:
            out.append(
                Finding(
                    "L012",
                    f"priority is {entry.priority!r}; expected one of {sorted(PRIORITIES)}",
                    entry.name,
                    _rel(package, package.manifest.path),
                )
            )


# --- L013 -------------------------------------------------------------------


def _equalities(claim: str) -> int:
    """Every `==` in the claim, at any bracketing depth.

    Counting only depth-zero equalities would miss the shape this rule exists
    for: `Bool.and(x == y, z == w)` is two claims in one law even though both
    equalities sit inside a call.
    """
    return claim.count("==")


def l013_atomic(package: Package, out: list[Finding]) -> None:
    laws_rel = _rel(package, package.laws.path) if package.laws.path else None
    for law in package.laws.laws:
        if _equalities(law.claim) > 1:
            out.append(
                Finding(
                    "L013",
                    "more than one equality: split the law so a failure names "
                    "one requirement",
                    law.name,
                    laws_rel,
                    law.line,
                )
            )


# --- L014 and L015 ----------------------------------------------------------


def _verify_hashes(
    package: Package, declared: Mapping[str, str], rule: str, source: str, out: list[Finding]
) -> None:
    for relative, expected in declared.items():
        path = package.root / relative
        if not path.exists():
            out.append(Finding(rule, f"{source} names {relative}, which does not exist"))
            continue
        actual = sha256(path)
        if actual != expected:
            out.append(
                Finding(
                    rule,
                    f"{source} records {expected[:12]}... but {relative} hashes to {actual[:12]}...",
                )
            )


def l014_manifest_hash(package: Package, out: list[Finding]) -> None:
    if not package.manifest.hashes:
        package.notes.append(
            "L014 not evaluated: the manifest declares no `hashes` or `law_sha256`"
        )
        return
    _verify_hashes(package, package.manifest.hashes, "L014", "the manifest", out)


def l015_provenance(package: Package, out: list[Finding]) -> None:
    if package.provenance is None:
        out.append(
            Finding(
                "L015",
                package.provenance_error
                or "provenance.yaml is absent, so the authoring chain cannot be checked",
            )
        )
        return
    artifacts = package.provenance.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        out.append(Finding("L015", "provenance.yaml declares no artifacts"))
        return
    declared: dict[str, str] = {}
    for item in artifacts:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            out.append(Finding("L015", "a provenance artifact entry has no `path`"))
            continue
        digest = item.get("sha256")
        if not isinstance(digest, str) or not digest.strip():
            out.append(
                Finding("L015", f"provenance entry {item['path']} has no `sha256`")
            )
            continue
        declared[item["path"]] = digest.strip()
    _verify_hashes(package, declared, "L015", "provenance.yaml", out)


# --- driver -----------------------------------------------------------------


def check(package: Package) -> list[Finding]:
    findings: list[Finding] = []
    for rule in (
        l001_witness,
        l002_presence,
        l003_traceability,
        l004_coverage,
        l005_hypothesis,
        l006_mutation,
        l007_escape_hatches,
        l008_naming,
        l009_duplicates,
        l010_symbols,
        l011_translation,
        l012_priority,
        l013_atomic,
        l014_manifest_hash,
        l015_provenance,
    ):
        rule(package, findings)
    for problem in package.laws.problems:
        findings.append(Finding("source", problem))
    return findings


def load_package(root: Path, mutation: Mapping[str, Any] | None = None) -> Package:
    from bendeda.laws.manifest import MANIFEST_NAME

    manifest = Manifest.load(root / MANIFEST_NAME)
    laws_path = root / "LAWS.bend"
    if not laws_path.exists():
        raise FileNotFoundError(f"{root}: no LAWS.bend")
    laws = parse_bend(laws_path.read_text(encoding="utf-8"), laws_path)
    model_path = root / "model.bend"
    model = parse_bend(model_path.read_text(encoding="utf-8"), model_path) if model_path.exists() else None
    bv_path = root / "bv.bend"
    bv = parse_bend(bv_path.read_text(encoding="utf-8"), bv_path) if bv_path.exists() else None

    provenance: Mapping[str, Any] | None = None
    provenance_error: str | None = None
    provenance_path = root / "provenance.yaml"
    if provenance_path.exists():
        try:
            provenance = read_yaml(provenance_path)
        except ValueError as exc:
            provenance_error = f"provenance.yaml could not be read: {exc}"
    return Package(
        root=root,
        manifest=manifest,
        laws=laws,
        model=model,
        bv=bv,
        provenance=provenance,
        provenance_error=provenance_error,
        mutation=mutation,
    )
