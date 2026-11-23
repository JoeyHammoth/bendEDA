# SPDX-License-Identifier: Apache-2.0
"""Read a Bend law file as data.

The lint rules need three things from `LAWS.bend`: the law names, their
parameters and their claim text; the definitions that fill them; and the line
each one starts on. This module extracts exactly that much.

It is a line-and-bracket scanner, not a Bend parser. Everything it cannot read
is recorded in `BendFile.problems` instead of being guessed at, because a lint
rule that silently skips a law is worse than no rule: the report says "clean"
for a file nobody inspected. `lint` turns a non-empty `problems` list into a
failure for the same reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

#: A block starts with one of these at column zero. Indentation is what makes
#: a line a body line; Bend has no other block delimiter at this level.
_TOP_LEVEL = re.compile(r"^(law|def|import|type)\b")
_LAW_HEAD = re.compile(r"^law\s+([A-Za-z_][\w.?]*)\s*:")
# A def head can carry a return annotation after its parameters, so the name is
# all this pattern claims; the parameter list is scanned by bracket, not regex.
_DEF_HEAD = re.compile(r"^def\s+([A-Za-z_][\w.?]*)")
_FOR_LINE = re.compile(r"^for\s*([+\-]?)\s*([A-Za-z_][\w]*)\s*:\s*(.+?)\s*$")

_OPENERS = {"(": ")", "[": "]", "{": "}"}


def _matching(text: str, start: int) -> int:
    """Index of the bracket that closes the one at `start`, or -1."""
    opener = text[start]
    closer = _OPENERS[opener]
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return index
    return -1


def _split_top_level(text: str, separator: str) -> tuple[str, str] | None:
    """Split at the last `separator` that sits outside brackets."""
    depth = 0
    cut = -1
    for index, char in enumerate(text):
        if char in _OPENERS:
            depth += 1
        elif char in _OPENERS.values():
            depth -= 1
        elif char == separator and depth == 0:
            cut = index
    if cut < 0:
        return None
    return text[:cut].strip(), text[cut + 1 :].strip()


@dataclass(frozen=True)
class Param:
    name: str
    type: str
    affine: bool = False  # written `+x` or `-x`: Bend bindings are affine
    hypothesis: bool = False  # the type is a proposition, i.e. a precondition

    @property
    def rendered(self) -> str:
        mark = "+" if self.affine else ""
        return f"{mark}{self.name}: {self.type}"


@dataclass(frozen=True)
class Law:
    name: str
    params: tuple[Param, ...]
    claim: str
    claim_type: str
    line: int
    raw: str = field(default="", compare=False)

    @property
    def conditional(self) -> bool:
        """A law with a proposition hypothesis only holds where it holds.

        Such a law is exactly the one the manifest must accompany with a
        witness (L001), because a checker that accepts it has said nothing
        about whether the hypothesis is ever reachable.
        """
        return any(p.hypothesis for p in self.params)


@dataclass(frozen=True)
class Definition:
    name: str
    params: tuple[str, ...]
    line: int
    raw: str = field(default="", compare=False)


@dataclass
class BendFile:
    path: Path | None
    text: str
    laws: list[Law] = field(default_factory=list)
    defs: list[Definition] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def law(self, name: str) -> Law | None:
        for law in self.laws:
            if law.name == name:
                return law
        return None

    def definition(self, name: str) -> Definition | None:
        for definition in self.defs:
            if definition.name == name:
                return definition
        return None

    def law_names(self) -> set[str]:
        return {law.name for law in self.laws}


def _blocks(text: str) -> list[tuple[str, int, list[str]]]:
    """Top-level blocks as (head line, 1-based line number, all lines)."""
    blocks: list[tuple[str, int, list[str]]] = []
    head: str | None = None
    start = 0
    lines: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        is_top = bool(line[:1]) and line[:1] not in (" ", "\t") and _TOP_LEVEL.match(stripped)
        if is_top:
            if head is not None:
                blocks.append((head, start, lines))
            head = stripped
            start = number
            lines = [line]
        elif head is not None:
            lines.append(line)
    if head is not None:
        blocks.append((head, start, lines))
    return blocks


def _parse_params(body: list[str]) -> tuple[list[Param], int]:
    params: list[Param] = []
    consumed = 0
    for line in body[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            consumed += 1
            continue
        if not stripped.startswith("for "):
            break
        match = _FOR_LINE.match(stripped)
        if not match:
            break
        mark, name, declared = match.groups()
        described = declared.strip()
        params.append(
            Param(
                name=name,
                type=described,
                affine=bool(mark),
                hypothesis=described.startswith("{"),
            )
        )
        consumed += 1
    return params, consumed


def _parse_law(head: str, start: int, body: list[str], problems: list[str]) -> Law:
    match = _LAW_HEAD.match(head)
    assert match is not None  # guarded by _blocks
    name = match.group(1)
    params, consumed = _parse_params(body)

    claim_lines: list[str] = []
    for line in body[1 + consumed :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        claim_lines.append(stripped)
    claim_text = " ".join(claim_lines)

    claim = claim_text
    claim_type = ""
    opened = claim_text.find("{")
    if opened >= 0:
        closed = _matching(claim_text, opened)
        if closed < 0:
            problems.append(f"law {name} at line {start}: '{{' is never closed")
            return Law(name, tuple(params), claim_text, "", start, "\n".join(body))
        inner = claim_text[opened + 1 : closed]
        split = _split_top_level(inner, ":")
        if split is None:
            problems.append(
                f"law {name} at line {start}: the claim has no ': <type>' annotation, "
                "so nothing says what the two sides are compared at"
            )
            claim, claim_type = inner.strip(), ""
        else:
            claim, claim_type = split
    elif not claim_text:
        problems.append(f"law {name} at line {start}: no claim")
    # A law with no braces declares a definition's type (Base uses this); it is
    # not a property and the claim rules skip it.
    return Law(name, tuple(params), claim, claim_type, start, "\n".join(body))


def _parse_def(head: str, start: int, body: list[str], problems: list[str]) -> Definition:
    match = _DEF_HEAD.match(head)
    assert match is not None
    name = match.group(1)
    opened = head.find("(")
    closed = _matching(head, opened) if opened >= 0 else -1
    raw_params = head[opened + 1 : closed] if opened >= 0 and closed > opened else ""
    params: list[str] = []
    if raw_params.strip():
        depth = 0
        current = ""
        for char in raw_params:
            if char in _OPENERS:
                depth += 1
            elif char in _OPENERS.values():
                depth -= 1
            if char == "," and depth == 0:
                params.append(current)
                current = ""
            else:
                current += char
        params.append(current)
    names = []
    for item in params:
        head_name = item.strip().lstrip("+-").split(":")[0].strip()
        if not head_name:
            problems.append(f"def {name} at line {start}: a parameter has no name")
            continue
        names.append(head_name)
    return Definition(name, tuple(names), start, "\n".join(body))


def parse(text: str, path: Path | None = None) -> BendFile:
    """Read a Bend source file into laws, definitions and imports."""
    parsed = BendFile(path=path, text=text)
    for head, start, body in _blocks(text):
        if head.startswith("import "):
            parsed.imports.append(head[len("import ") :].strip())
        elif head.startswith("law "):
            parsed.laws.append(_parse_law(head, start, body, parsed.problems))
        elif head.startswith("def "):
            parsed.defs.append(_parse_def(head, start, body, parsed.problems))
    return parsed


def load(path: Path) -> BendFile:
    return parse(path.read_text(encoding="utf-8"), path)
