# SPDX-License-Identifier: Apache-2.0
"""`bendeda law mutate`: model mutation adequacy (gate LA3).

A law set can be proved and still say nothing. The defence is pressure: change
the model in ways an implementer plausibly would, and see whether some law
notices. A law that survives every mutant is model-insensitive (rule L006), and
a mutant that survives every law is a behaviour no law constrains.

Bend 2.0.40 prints only the first failing law, so a single run cannot say which
laws a mutant falsified. Each law is therefore isolated into its own file: the
mutated model is inlined ahead of the law and the proofs it depends on, and the
checker is run once per law per mutant. That costs compiler runs, and it is the
only way to attribute a kill.

Inlining the model is deliberate. `import model` is rejected at this pin
("expected: an import ('import Base', or 'import <path> as <Name>')"), and a
mutation tool cannot depend on an import form the checker refuses.

The catalogue has two halves. Operator swaps and literal bumps need arithmetic,
so they say nothing about a model that is a finite transition table; for those,
the catalogue swaps the bodies of sibling `match` arms with the same bound names,
replaces a nullary constructor with another of the same declared type, and bumps
a bare numeric literal that stands alone as a definition's result. All three keep
the program well typed, which is the point: a mutant that stops compiling is not
a killed mutant.

The bare-literal case matters for a decode. `count` returning `2n` is a total
function into `Nat`; nothing about the occupancy type stops it returning `3n`, so
a bound law over `count` is falsifiable and a catalogue that only bumps literals
on arithmetic lines cannot see that.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from bendeda.canary.runner import PASS, FAIL, Checker, build_checker, run_argv
from bendeda.laws.source import BendFile, load as load_bend

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_NOTHING_MEASURED = 3

#: Binary operator swaps that keep the program well typed, so a surviving mutant
#: means "no law noticed" rather than "the file no longer compiles".
SWAPS: tuple[tuple[str, str], ...] = (
    ("U32.add", "U32.sub"),
    ("U32.sub", "U32.add"),
    ("Word.add", "Word.sub"),
    ("Word.and", "Word.or"),
    ("Word.xor", "Word.or"),
    ("Bool.and", "Bool.or"),
    ("Bool.or", "Bool.and"),
    ("Nat.add", "Nat.sub"),
    ("Nat.sub", "Nat.add"),
    ("Nat.mul", "Nat.add"),
    ("Nat.min", "Nat.max"),
    ("Nat.is_lt", "Nat.is_le"),
    ("Nat.is_le", "Nat.is_lt"),
    ("Nat.is_gt", "Nat.is_ge"),
    ("Cmp.is_lt", "Cmp.is_le"),
)

_ARITHMETIC = re.compile(r"\b(?:add|sub|mul|shln|shrn|is_lt|is_le|is_gt|is_ge)\b")
_TYPE_HEAD = re.compile(r"^type\s+(\w+)\s+is\s+\w+\s*:")
_TYPE_CTOR = re.compile(r"^(\s+)(\w+)\{([^}]*)\}\s*$")
_MATCH = re.compile(r"^(\s*)match\b.*:\s*$")
_CASE = re.compile(r"^(\s*)case\s+(.+?):\s*$")
_CONSTRUCT = re.compile(r"\b([A-Z]\w*)\{\}")
#: A line that is nothing but a numeric literal (and an optional comment). These
#: are the results of a decode such as `count`, where the value is the whole point
#: of the line and there is no operator to swap.
_BARE_LITERAL = re.compile(r"^(\s*)(\d+)(n?)(\s*(?:#.*)?)$")

#: Nullary constructors the checker provides, so a `Bool` result can be flipped
#: in a model that does not declare `Bool` itself.
_BUILTIN_NULLARY: dict[str, str] = {"True": "Bool", "False": "Bool"}
_NUMBER = re.compile(r"(?<![\w.\"])(\d+)(n?)(?![\w.\"])")
_IDENTIFIER = re.compile(r"[A-Za-z_][\w.]*")
_IMPORT = re.compile(r"^import\b.*$", re.MULTILINE)


@dataclass(frozen=True)
class Mutant:
    id: str
    description: str
    line: int
    text: str


@dataclass(frozen=True)
class Arm:
    """One `case` arm, with the 0-based half-open slice of its body."""

    line: int
    pattern: str
    bindings: frozenset[str]
    start: int
    end: int


@dataclass(frozen=True)
class IsolatedLaw:
    name: str
    text: str


@dataclass
class MutantOutcome:
    id: str
    description: str
    line: int
    killed: list[str] = field(default_factory=list)
    survived: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class MutationReport:
    model: str
    laws: list[str]
    mutants: list[MutantOutcome]
    checker: str
    notes: list[str] = field(default_factory=list)

    def law_records(self) -> dict[str, dict[str, int]]:
        records: dict[str, dict[str, int]] = {name: {"killed_by": 0, "total": 0} for name in self.laws}
        for mutant in self.mutants:
            for name in mutant.killed:
                records.setdefault(name, {"killed_by": 0, "total": 0})["killed_by"] += 1
            for name in mutant.killed + mutant.survived:
                records.setdefault(name, {"killed_by": 0, "total": 0})["total"] += 1
        return records

    @property
    def mutants_killed(self) -> int:
        return sum(1 for mutant in self.mutants if mutant.killed)

    @property
    def kill_rate(self) -> float:
        measured = [m for m in self.mutants if m.killed or m.survived]
        return len([m for m in measured if m.killed]) / len(measured) if measured else 0.0

    @property
    def survivors(self) -> list[str]:
        return [name for name, record in self.law_records().items() if record["killed_by"] == 0]

    def exit_code(self, min_mutants: int = 20, min_kill: float = 0.9) -> int:
        measured = [m for m in self.mutants if m.killed or m.survived]
        if not measured:
            return EXIT_NOTHING_MEASURED
        if len(self.mutants) < min_mutants:
            return EXIT_FAIL
        if self.kill_rate < min_kill:
            return EXIT_FAIL
        if self.survivors:
            return EXIT_FAIL
        if any(m.errors for m in self.mutants):
            return EXIT_FAIL
        return EXIT_OK

    def as_json(
        self,
        min_mutants: int = 20,
        min_kill: float = 0.9,
        environment: Mapping[str, str] | None = None,
    ) -> dict:
        payload = {
            "model": self.model,
            "checker": self.checker,
            "laws": self.law_records(),
            "mutants": [
                {
                    "id": m.id,
                    "description": m.description,
                    "line": m.line,
                    "killed": m.killed,
                    "survived": m.survived,
                    "errors": m.errors,
                }
                for m in self.mutants
            ],
            "summary": {
                "mutants": len(self.mutants),
                "mutants_killed": self.mutants_killed,
                "kill_rate": round(self.kill_rate, 4),
                "min_mutants": min_mutants,
                "min_kill": min_kill,
                "survivors": self.survivors,
                "notes": self.notes,
                "ok": self.exit_code(min_mutants, min_kill) == EXIT_OK,
            },
        }
        if environment is not None:
            payload["environment"] = dict(environment)
        return payload


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def constructor_types(lines: Sequence[str]) -> tuple[dict[str, str], set[int]]:
    """Nullary constructor -> declaring type, plus the lines that declare them."""
    types: dict[str, str] = {}
    declarations: set[int] = set()
    current: str | None = None
    for number, line in enumerate(lines, start=1):
        head = _TYPE_HEAD.match(line)
        if head:
            current = head.group(1)
            continue
        if current is None:
            continue
        if line.strip() and indent_of(line) == 0:
            current = None
            continue
        ctor = _TYPE_CTOR.match(line)
        if ctor and not ctor.group(3).strip():
            types[ctor.group(2)] = current
            declarations.add(number)
    return types, declarations


def match_arms(lines: Sequence[str]) -> list[tuple[int, list[Arm]]]:
    """Every `match`, with its sibling arms in source order."""
    blocks: list[tuple[int, list[Arm]]] = []
    for index, line in enumerate(lines):
        head = _MATCH.match(line)
        if not head:
            continue
        match_indent = indent_of(line)
        arm_indent: int | None = None
        arms: list[Arm] = []
        cursor = index + 1
        while cursor < len(lines):
            current = lines[cursor]
            if not current.strip():
                cursor += 1
                continue
            current_indent = indent_of(current)
            if current_indent <= match_indent:
                break
            case = _CASE.match(current)
            if case and (arm_indent is None or current_indent == arm_indent):
                arm_indent = current_indent
                start = cursor + 1
                end = start
                probe = start
                while probe < len(lines):
                    nxt = lines[probe]
                    if not nxt.strip():
                        probe += 1
                        continue
                    if indent_of(nxt) <= current_indent:
                        break
                    end = probe + 1
                    probe += 1
                bindings = frozenset(
                    name.strip().lstrip("+")
                    for group in re.findall(r"\{([^}]*)\}", case.group(2))
                    for name in group.split(",")
                    if name.strip()
                )
                arms.append(Arm(cursor + 1, case.group(2).strip(), bindings, start, end))
                cursor = max(end, cursor + 1)
                continue
            cursor += 1
        blocks.append((index + 1, arms))
    return blocks


def branch_swaps(lines: Sequence[str], arms: Sequence[Arm]) -> list[tuple[int, str, list[str]]]:
    """Exchange the bodies of two arms that bind the same names."""
    edits: list[tuple[int, str, list[str]]] = []
    for first in range(len(arms)):
        for second in range(first + 1, len(arms)):
            a, b = arms[first], arms[second]
            if a.bindings != b.bindings:
                continue
            body_a = lines[a.start : a.end]
            body_b = lines[b.start : b.end]
            if body_a == body_b:
                continue
            edited = list(lines)
            edited[b.start : b.end] = body_a
            edited[a.start : a.end] = body_b
            edits.append((a.line, f"swap arms {a.pattern} / {b.pattern}", edited))
    return edits


def constructor_choices(
    lines: Sequence[str],
    types: Mapping[str, str],
    declarations: set[int],
) -> list[tuple[int, str, list[str]]]:
    """Replace a nullary constructor with another of its declared type."""
    effective = dict(_BUILTIN_NULLARY)
    effective.update(types)
    alternatives = {
        name: sorted(other for other, kind in effective.items() if kind == own and other != name)
        for name, own in effective.items()
    }
    edits: list[tuple[int, str, list[str]]] = []
    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith("#") or number in declarations:
            continue
        if _CASE.match(line) or _MATCH.match(line):
            continue
        for site in _CONSTRUCT.finditer(line):
            for alternative in alternatives.get(site.group(1), ()):
                edited = list(lines)
                edited[number - 1] = line[: site.start()] + f"{alternative}{{}}" + line[site.end() :]
                edits.append((number, f"{site.group(1)}{{}} -> {alternative}{{}}", edited))
    return edits


def candidates(model_text: str, max_mutants: int = 48) -> list[Mutant]:
    """Semantic mutants, one edit each, in source order."""
    lines = model_text.splitlines()
    sites: list[tuple[int, str, list[str]]] = []

    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith("#"):
            continue
        for old, new in SWAPS:
            for match in re.finditer(rf"\b{re.escape(old)}\b", line):
                edited = list(lines)
                edited[number - 1] = line[: match.start()] + new + line[match.end() :]
                sites.append((number, f"{old} -> {new}", edited))
        if _ARITHMETIC.search(line):
            match = _NUMBER.search(line)
            if match:
                bumped = f"{int(match.group(1)) + 1}{match.group(2)}"
                edited = list(lines)
                edited[number - 1] = line[: match.start()] + bumped + line[match.end() :]
                sites.append((number, f"literal {match.group(1)} -> {bumped}", edited))
        else:
            bare = _BARE_LITERAL.match(line.rstrip())
            if bare:
                bumped = f"{int(bare.group(2)) + 1}{bare.group(3)}"
                edited = list(lines)
                edited[number - 1] = f"{bare.group(1)}{bumped}{bare.group(4)}"
                sites.append((number, f"literal {bare.group(2)}{bare.group(3)} -> {bumped}", edited))

    types, declarations = constructor_types(lines)
    sites.extend(constructor_choices(lines, types, declarations))
    for _, arms in match_arms(lines):
        sites.extend(branch_swaps(lines, arms))

    sites.sort(key=lambda site: site[0])
    mutants: list[Mutant] = []
    seen: set[str] = set()
    for number, description, edited in sites:
        text = "\n".join(edited)
        if text in seen:
            continue
        seen.add(text)
        mutants.append(Mutant(f"m{len(mutants) + 1:03d}", description, number, text))
        if len(mutants) >= max_mutants:
            break
    return mutants


def strip_imports(text: str) -> str:
    return _IMPORT.sub("", text).strip("\n")


def isolate_laws(laws: BendFile, prelude: str) -> list[IsolatedLaw]:
    """One file per law: the prelude, the law, its proof, and its dependencies."""
    # A law and its proof are two blocks with the same name. Both must be
    # scanned: the proof is where helper lemmas are called, and the law's claim
    # is where model definitions are named.
    blocks_by_name: dict[str, list[str]] = {}
    blocks: list[tuple[int, str]] = []
    for law in laws.laws:
        blocks_by_name.setdefault(law.name, []).append(law.raw)
        blocks.append((law.line, law.raw))
    for definition in laws.defs:
        blocks_by_name.setdefault(definition.name, []).append(definition.raw)
        blocks.append((definition.line, definition.raw))

    def closure(start: str) -> set[str]:
        selected: set[str] = set()
        queue = [start]
        while queue:
            name = queue.pop()
            if name in selected:
                continue
            own = blocks_by_name.get(name)
            if not own:
                continue
            selected.add(name)
            for block in own:
                for identifier in _IDENTIFIER.findall(block):
                    if identifier in blocks_by_name:
                        queue.append(identifier)
        return selected

    isolated: list[IsolatedLaw] = []
    for law in laws.laws:
        selected = closure(law.name)
        ordered = [raw for _, raw in sorted(blocks, key=lambda item: item[0]) if _name_of(raw) in selected]
        text = "import Base\n\n" + prelude.strip("\n") + "\n\n" + "\n\n".join(ordered) + "\n"
        isolated.append(IsolatedLaw(law.name, text))
    return isolated


def _name_of(block: str) -> str:
    match = re.match(r"^(?:law|def)\s+([A-Za-z_][\w.]*)", block)
    return match.group(1) if match else ""


def _first_line(output: str) -> str:
    for line in output.splitlines():
        if line.strip():
            return line.strip()[:200]
    return ""


def run_mutation(
    *,
    model_text: str,
    laws_file: BendFile,
    checker: Checker,
    workdir: Path,
    prelude: str = "",
    max_mutants: int = 48,
    timeout: int = 180,
    invoke: Callable[[Sequence[str], Path, int], tuple[int, str]] = run_argv,
    progress: Callable[[int, int, Mutant], None] | None = None,
) -> MutationReport:
    isolated = isolate_laws(laws_file, strip_imports(model_text) + ("\n\n" + prelude if prelude else ""))
    mutants = candidates(model_text, max_mutants=max_mutants)
    report = MutationReport(
        model=str(getattr(laws_file, "path", "") or ""),
        laws=[law.name for law in isolated],
        mutants=[],
        checker=checker.label,
    )
    if not mutants:
        report.notes.append("the model has no site this catalogue can mutate")
        return report

    workdir.mkdir(parents=True, exist_ok=True)
    for index, mutant in enumerate(mutants, start=1):
        if progress:
            progress(index, len(mutants), mutant)
        outcome = MutantOutcome(mutant.id, mutant.description, mutant.line)
        mutant_dir = workdir / mutant.id
        mutant_dir.mkdir(parents=True, exist_ok=True)
        for position, law in enumerate(isolate_laws(laws_file, strip_imports(mutant.text) + ("\n\n" + prelude if prelude else ""))):
            path = mutant_dir / f"law_{position:02d}.bend"
            path.write_text(law.text, encoding="utf-8", newline="")
            try:
                relative = path.relative_to(checker.cwd).as_posix()
            except ValueError:
                relative = path.as_posix()
            _, output = invoke(checker.command(relative), checker.cwd, timeout)
            if PASS in output:
                outcome.survived.append(law.name)
            elif FAIL in output and "TODO" not in output:
                # A law with no proof, or with `?TODO` left in it, also reports
                # SOME PROOFS FAIL. That is an incomplete file, not a refutation,
                # and counting it as a kill would credit the catalogue with
                # catching a bug it never saw.
                outcome.killed.append(law.name)
            else:
                outcome.errors.append(f"{law.name}: {_first_line(output) or 'no verdict'}")
        report.mutants.append(outcome)
    return report


def format_table(report: MutationReport) -> str:
    lines = ["mutant  line  killed by                                  survived / errors"]
    for mutant in report.mutants:
        killed = ", ".join(mutant.killed) or "-"
        other = ", ".join(mutant.survived) or "-"
        if mutant.errors:
            other += f" (errors: {'; '.join(mutant.errors)})"
        lines.append(f"{mutant.id:<7} {mutant.line:>4}  {killed:<42} {other}")
    return "\n".join(lines)


def write_report(
    report: MutationReport,
    path: Path,
    min_mutants: int,
    min_kill: float,
    environment: Mapping[str, str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.as_json(min_mutants, min_kill, environment), indent=2) + "\n",
        encoding="utf-8",
        newline="",
    )


def _resolve_inputs(paths: Iterable[str], laws: str | None, bv: str | None) -> tuple[Path, Path, Path | None]:
    model: Path | None = None
    laws_path: Path | None = Path(laws) if laws else None
    bv_path: Path | None = Path(bv) if bv else None
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            model = path / "model.bend"
            laws_path = laws_path or path / "LAWS.bend"
            if bv_path is None and (path / "bv.bend").exists():
                bv_path = path / "bv.bend"
        elif path.suffix == ".bend":
            if laws_path is None:
                laws_path = path
            else:
                model = path
    if model is None or not model.exists():
        raise FileNotFoundError("no model.bend: pass a task directory, or a .bend file with --laws")
    if laws_path is None or not laws_path.exists():
        raise FileNotFoundError("no LAWS.bend: pass a task directory, or --laws <file>")
    return model, laws_path, bv_path


def cmd_mutate(args) -> int:
    try:
        model_path, laws_path, bv_path = _resolve_inputs(args.paths, args.laws, args.bv)
    except FileNotFoundError as exc:
        print(f"bendeda law mutate: {exc}", file=sys.stderr)
        return 2

    checker = build_checker(
        local=args.local,
        root=Path.cwd(),
        bun=args.bun,
        bend_cli=args.bend_cli,
        image=args.image,
        docker=args.docker,
    )
    if isinstance(checker, str):
        print(f"bendeda law mutate: cannot run the checker: {checker}", file=sys.stderr)
        print("  nothing was measured, so this is not a pass (exit 3).", file=sys.stderr)
        return EXIT_NOTHING_MEASURED

    prelude = strip_imports(bv_path.read_text(encoding="utf-8")) if bv_path else ""
    laws_file = load_bend(laws_path)
    workdir = Path(".bend-cache") / "mutate" / (model_path.parent.name or "model")
    if not args.quiet:
        print(
            f"law mutate: {model_path} against {len(laws_file.laws)} law(s) through {checker.label}",
            file=sys.stderr,
        )
    report = run_mutation(
        model_text=model_path.read_text(encoding="utf-8"),
        laws_file=laws_file,
        checker=checker,
        workdir=workdir,
        prelude=prelude,
        max_mutants=args.max_mutants,
        timeout=args.timeout,
    )
    report.model = model_path.as_posix()

    from bendeda import provenance

    environment = provenance.environment(checker, args.docker)
    if args.out:
        write_report(report, Path(args.out), args.min_mutants, args.min_kill, environment)
    if args.json:
        print(
            json.dumps(
                report.as_json(args.min_mutants, args.min_kill, environment), indent=2
            )
        )
    elif not args.quiet:
        print(format_table(report))
        for note in report.notes:
            print(f"law mutate: note: {note}", file=sys.stderr)

    code = report.exit_code(args.min_mutants, args.min_kill)
    summary = (
        f"law mutate: {len(report.mutants)} mutant(s), "
        f"{report.mutants_killed} killed by at least one law, "
        f"kill rate {report.kill_rate:.2f}"
    )
    if report.survivors:
        summary += f", {len(report.survivors)} law(s) survived every mutant"
    if len(report.mutants) < args.min_mutants:
        summary += f"; below the pre-registered minimum of {args.min_mutants} mutants"
    print(summary, file=sys.stderr if code else sys.stdout)
    return code
