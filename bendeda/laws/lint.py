# SPDX-License-Identifier: Apache-2.0
"""`bendeda law lint`: run rules L001-L015 over task packages.

Exit codes follow the `canary` convention, for the same reason:

  0  every applicable rule ran and found nothing
  1  at least one rule fired (or a package could not be read)
  3  nothing was linted, because no task package was found

A missing package is not a clean package. An empty directory must not print
"0 findings" and exit 0, because that is the shape of a gate that passed
without running.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from bendeda.laws.manifest import MANIFEST_NAME, ManifestError
from bendeda.laws.rules import RULES, Finding, check, load_package, Package

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_NOTHING_LINTED = 3


@dataclass
class PackageResult:
    root: Path
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    laws: int = 0
    error: str | None = None


@dataclass
class Report:
    results: list[PackageResult] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def findings(self) -> list[Finding]:
        return [finding for result in self.results for finding in result.findings]

    @property
    def notes(self) -> list[str]:
        return [note for result in self.results for note in result.notes]

    @property
    def laws(self) -> int:
        return sum(result.laws for result in self.results)

    def exit_code(self) -> int:
        if not self.results:
            return EXIT_NOTHING_LINTED
        if self.findings or any(result.error for result in self.results):
            return EXIT_FINDINGS
        return EXIT_OK

    def as_json(self) -> dict[str, Any]:
        return {
            "packages": [result.root.as_posix() for result in self.results],
            "skipped": self.skipped,
            "laws": self.laws,
            "findings": [finding.as_json() for finding in self.findings],
            "notes": self.notes,
            "rules": RULES,
            "ok": self.exit_code() == EXIT_OK,
        }


def discover(paths: list[str]) -> tuple[list[Path], list[str]]:
    """Task package roots, and the paths that contained no package."""
    found: list[Path] = []
    skipped: list[str] = []
    for raw in paths:
        path = Path(raw)
        if path.is_file() and path.name == MANIFEST_NAME:
            found.append(path.parent)
            continue
        if path.is_file():
            skipped.append(f"{raw}: not a {MANIFEST_NAME}")
            continue
        if not path.exists():
            skipped.append(f"{raw}: does not exist")
            continue
        if (path / MANIFEST_NAME).exists():
            found.append(path)
            continue
        packages = sorted({item.parent for item in path.rglob(MANIFEST_NAME)})
        if packages:
            found.extend(packages)
        else:
            skipped.append(f"{raw}: no {MANIFEST_NAME} under it")
    # Preserve order while removing duplicates (a package can match twice).
    unique = list(dict.fromkeys(found))
    return unique, skipped


def run(paths: list[str], mutation: Mapping[str, Any] | None = None) -> Report:
    report = Report()
    roots, skipped = discover(paths)
    report.skipped = skipped
    for root in roots:
        result = PackageResult(root=root)
        try:
            package: Package = load_package(root, mutation=mutation)
        except (ManifestError, FileNotFoundError) as exc:
            result.error = str(exc)
            result.findings.append(
                Finding("package", f"could not be read: {exc}", path=root.as_posix())
            )
            report.results.append(result)
            continue
        result.laws = len(package.laws.laws)
        result.findings = check(package)
        result.notes = package.notes
        report.results.append(result)
    return report


def read_mutation(path: str | None) -> Mapping[str, Any] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def format_report(report: Report) -> str:
    lines: list[str] = []
    for result in report.results:
        if result.error:
            lines.append(f"{result.root}: unreadable ({result.error})")
            continue
        lines.append(f"{result.root}: {result.laws} law(s), {len(result.findings)} finding(s)")
        for finding in result.findings:
            lines.append(f"  {finding.render()}")
        for note in result.notes:
            lines.append(f"  note: {note}")
    for item in report.skipped:
        lines.append(f"skipped {item}")
    return "\n".join(lines)


def cmd_lint(args) -> int:
    try:
        mutation = read_mutation(getattr(args, "mutation", None))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"bendeda law lint: cannot read the mutation report: {exc}", file=sys.stderr)
        return 2

    report = run(list(args.paths), mutation=mutation)

    if args.json:
        print(json.dumps(report.as_json(), indent=2))
    elif not getattr(args, "quiet", False):
        rendered = format_report(report)
        if rendered:
            print(rendered)

    if not report.results:
        print(
            "bendeda law lint: no task package was linted "
            f"({len(report.skipped)} path(s) skipped), so this is not a pass (exit 3)",
            file=sys.stderr,
        )
        return EXIT_NOTHING_LINTED

    counts = {rule: 0 for rule in RULES}
    for finding in report.findings:
        counts[finding.rule] = counts.get(finding.rule, 0) + 1
    fired = {rule: count for rule, count in counts.items() if count}
    summary = (
        f"law lint: {len(report.results)} package(s), {report.laws} law(s), "
        f"{len(report.findings)} finding(s)"
    )
    if fired:
        summary += " (" + ", ".join(f"{rule}x{count}" for rule, count in sorted(fired.items())) + ")"
    print(summary, file=sys.stderr if report.exit_code() else sys.stdout)
    if report.notes and not getattr(args, "quiet", False):
        for note in dict.fromkeys(report.notes):
            print(f"law lint: note: {note}", file=sys.stderr)
    return report.exit_code()
