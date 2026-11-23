# SPDX-License-Identifier: Apache-2.0
"""The proof escape hatches (PEH), enumerated against the pinned checker.

Appendix H.8: a proof that contains any PEH construct is *not closed*. The list
lives here, in code, because rule L007 and the harness both consume it; the
prose version in `docs/proof_cookbook.md` is written from this table and a test
keeps the two in step.

Every entry was checked against Bend 2.0.40's own parser (`.bend-cache/.../bend2/bend.ts`),
not against the guide, because the guide and the released grammar disagree in
places (the `def f?` shorthand is in the grammar; the guide never mentions it).

Two entries are not constructs but promises the checker cannot see through:

* a Base definition that is itself `@unsafe` — calling `Array.fork`,
  `Array.join` or `Array.get_unchecked` imports Base's promise into the proof;
* a `TODO` marker, which the checker ignores but which means the file is not
  finished.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class EscapeHatch:
    id: str
    name: str
    pattern: str
    why: str
    instead: str

    @property
    def regex(self) -> re.Pattern[str]:
        return re.compile(self.pattern)


#: Ordered: `?TODO` must be tested before the general named hole, and the bare
#: `TODO` marker must not fire on `?TODO`.
PEH: tuple[EscapeHatch, ...] = (
    EscapeHatch(
        "PEH-01",
        "@unsafe",
        r"@unsafe\b",
        "an unsafe definition opts out of the wall: its self-calls skip the "
        "descent check, its binder domains are accepted at any kind, and it may "
        "call an unfilled law or a definition below it",
        "restructure so the recursion descends on a strict subterm",
    ),
    EscapeHatch(
        "PEH-02",
        "def name?",
        r"\bdef\s+[A-Za-z_][\w.]*\?\s*\(",
        "the grammar defines `def f?(..)` as `@unsafe def f(..)`, so the "
        "question mark is the same escape hatch written shorter",
        "write `def f(..)` and prove the descent",
    ),
    EscapeHatch(
        "PEH-03",
        "?TODO",
        r"\?TODO\b",
        "a TODO hole checks at any goal and marks the book incomplete; it is "
        "an admission that the proof is unfinished, not a placeholder the "
        "checker accepts as proved",
        "replace the hole with the term that inhabits the goal",
    ),
    EscapeHatch(
        "PEH-04",
        "a named hole",
        r"\?(?!TODO\b)[A-Za-z_][A-Za-z0-9_]*",
        "a named hole fails every check and is shown against the goal; leaving "
        "one in a file makes the whole book fail, but a report that counted it "
        "as a proof attempt would be wrong",
        "fill the hole, or delete it and write the term",
    ),
    EscapeHatch(
        "PEH-05",
        "a foreign body",
        r"^\s+import\s+\"",
        "a definition whose body is `import \"...\"` is a promise: the checker "
        "reads the body as given, like `@unsafe`",
        "define the function in Bend, or isolate it behind a declared module "
        "boundary outside the proof",
    ),
    EscapeHatch(
        "PEH-06",
        "a Base definition that is @unsafe",
        r"\bArray\.(?:fork|join|get_unchecked)\b",
        "these three Base definitions are `@unsafe` at the pin, so a law or "
        "proof that calls one inherits a promise the checker did not discharge",
        "use the safe Base API, or state the property the unsafe call relies on",
    ),
    EscapeHatch(
        "PEH-07",
        "a TODO marker",
        r"(?<!\?)\bTODO\b",
        "the checker ignores comments, so a TODO in a checked file parses and "
        "checks; the file is still unfinished",
        "remove the marker by finishing the work, or move it to an issue",
    ),
)


@dataclass(frozen=True)
class Hit:
    line: int
    entry: EscapeHatch
    excerpt: str

    def render(self, path: str) -> str:
        return f"{path}:{self.line}: {self.entry.id} {self.entry.name}: {self.excerpt}"


def by_id(identifier: str) -> EscapeHatch:
    for entry in PEH:
        if entry.id == identifier:
            return entry
    raise KeyError(identifier)


def scan(text: str) -> list[Hit]:
    """Every escape hatch in `text`, one hit per line and entry.

    Comment lines are skipped: the cookbook and BendBV talk about `@unsafe` in
    prose, and a scanner that flagged its own documentation would be turned off
    within a day.
    """
    hits: list[Hit] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        for entry in PEH:
            if entry.regex.search(line):
                hits.append(Hit(number, entry, line.strip()[:120]))
    return hits
