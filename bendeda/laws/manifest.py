# SPDX-License-Identifier: Apache-2.0
"""Read `laws.manifest.yaml` without a third-party dependency.

The package has no runtime dependencies on purpose (see `bendeda/__init__.py`),
so this is a reader for the YAML subset the manifest schema uses: block
mappings, block lists, flow lists and maps, quoted strings, booleans, null and
integers. Anything outside that subset raises `ManifestError` with the line
number.

That strictness is deliberate. A permissive reader that turned an unsupported
construct into a string would let a manifest declare `priority: core` in a form
the linter cannot see, and the lint report would be clean about metadata it
never read.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

MANIFEST_NAME = "laws.manifest.yaml"

_OPENERS = {"[": "]", "{": "}", "(": ")"}


class ManifestError(ValueError):
    """The manifest uses a construct this reader does not support."""


def _strip_comment(line: str) -> str:
    quoted: str | None = None
    for index, char in enumerate(line):
        if quoted:
            if char == quoted:
                quoted = None
        elif char in ("'", '"'):
            quoted = char
        elif char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index]
    return line


def _scan(lines: list[str]) -> list[tuple[int, str, int]]:
    scanned: list[tuple[int, str, int]] = []
    for number, raw in enumerate(lines, start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ManifestError(f"line {number}: tabs are not indentation in YAML")
        stripped = _strip_comment(raw).rstrip()
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        scanned.append((indent, stripped.strip(), number))
    return scanned


def _split_key(content: str, number: int) -> tuple[str, str]:
    depth = 0
    quoted: str | None = None
    for index, char in enumerate(content):
        if quoted:
            if char == quoted:
                quoted = None
        elif char in ("'", '"'):
            quoted = char
        elif char in _OPENERS:
            depth += 1
        elif char in _OPENERS.values():
            depth -= 1
        elif char == ":" and depth == 0:
            return content[:index].strip(), content[index + 1 :].strip()
    raise ManifestError(f"line {number}: expected 'key: value', found {content!r}")


def _flow(text: str, number: int) -> Any:
    text = text.strip()
    if text.startswith("["):
        if not text.endswith("]"):
            raise ManifestError(f"line {number}: flow list is not closed")
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_scalar(item, number) for item in _split_flow(inner, number)]
    if text.startswith("{"):
        if not text.endswith("}"):
            raise ManifestError(f"line {number}: flow map is not closed")
        inner = text[1:-1].strip()
        result: dict[str, Any] = {}
        if not inner:
            return result
        for item in _split_flow(inner, number):
            key, value = _split_key(item, number)
            result[key] = _scalar(value, number)
        return result
    raise ManifestError(f"line {number}: not a flow collection: {text!r}")


def _split_flow(inner: str, number: int) -> list[str]:
    parts: list[str] = []
    depth = 0
    quoted: str | None = None
    current = ""
    for char in inner:
        if quoted:
            current += char
            if char == quoted:
                quoted = None
            continue
        if char in ("'", '"'):
            quoted = char
            current += char
        elif char in _OPENERS:
            depth += 1
            current += char
        elif char in _OPENERS.values():
            depth -= 1
            current += char
        elif char == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        parts.append(current.strip())
    if depth != 0:
        raise ManifestError(f"line {number}: unbalanced brackets in a flow collection")
    return parts


def _scalar(text: str, number: int) -> Any:
    text = text.strip()
    if not text:
        return None
    if text[0] in "[{":
        return _flow(text, number)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    lowered = text.lower()
    if lowered in ("true", "yes"):
        return True
    if lowered in ("false", "no"):
        return False
    if lowered in ("null", "~"):
        return None
    if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
        return int(text)
    return text


def _parse_block(
    lines: list[tuple[int, str, int]], index: int, indent: int
) -> tuple[Any, int]:
    if index >= len(lines):
        return None, index
    if lines[index][1].startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_list(
    lines: list[tuple[int, str, int]], index: int, indent: int
) -> tuple[Any, int]:
    items: list[Any] = []
    while index < len(lines) and lines[index][0] == indent and lines[index][1].startswith("- "):
        number = lines[index][2]
        rest = lines[index][1][2:].strip()
        index += 1
        if not rest:
            if index < len(lines) and lines[index][0] > indent:
                value, index = _parse_block(lines, index, lines[index][0])
            else:
                value = None
            items.append(value)
            continue
        if ":" not in rest:
            items.append(_scalar(rest, number))
            continue
        key, raw = _split_key(rest, number)
        item: dict[str, Any] = {}
        if raw:
            item[key] = _scalar(raw, number)
        elif index < len(lines) and lines[index][0] > indent:
            item[key], index = _parse_block(lines, index, lines[index][0])
        else:
            item[key] = None
        while index < len(lines) and lines[index][0] > indent and not lines[index][1].startswith("- "):
            child_indent = lines[index][0]
            child_key, child_raw = _split_key(lines[index][1], lines[index][2])
            index += 1
            if child_raw:
                item[child_key] = _scalar(child_raw, number)
            elif index < len(lines) and lines[index][0] > child_indent:
                item[child_key], index = _parse_block(lines, index, lines[index][0])
            else:
                item[child_key] = None
        items.append(item)
    return items, index


def _parse_mapping(
    lines: list[tuple[int, str, int]], index: int, indent: int
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines) and lines[index][0] == indent and not lines[index][1].startswith("- "):
        number = lines[index][2]
        key, raw = _split_key(lines[index][1], number)
        index += 1
        if raw:
            result[key] = _scalar(raw, number)
        elif index < len(lines) and lines[index][0] > indent:
            result[key], index = _parse_block(lines, index, lines[index][0])
        elif index < len(lines) and lines[index][0] == indent and lines[index][1].startswith("- "):
            result[key], index = _parse_list(lines, index, indent)
        else:
            result[key] = None
    return result, index


def parse_text(text: str) -> dict[str, Any]:
    lines = _scan(text.splitlines())
    if not lines:
        return {}
    value, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ManifestError(
            f"line {lines[index][2]}: unexpected indentation or a second document"
        )
    if not isinstance(value, dict):
        raise ManifestError("the manifest must be a mapping at the top level")
    return value


def read(path: Path) -> dict[str, Any]:
    return parse_text(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class LawEntry:
    id: str
    name: str
    law_class: str
    priority: str | None
    requirements: tuple[str, ...]
    witness: str | None
    translation: Mapping[str, Any] | None
    raw: Mapping[str, Any]

    @property
    def is_negative_control(self) -> bool:
        return self.law_class == "L-NEG"


@dataclass(frozen=True)
class Manifest:
    task: str
    path: Path
    laws: tuple[LawEntry, ...]
    requirements: tuple[str, ...] | None
    conformance_only: tuple[str, ...]
    oracle_only: tuple[str, ...]
    hashes: Mapping[str, str]
    raw: Mapping[str, Any]

    @property
    def by_name(self) -> dict[str, LawEntry]:
        return {entry.name: entry for entry in self.laws}

    @property
    def by_id(self) -> dict[str, LawEntry]:
        return {entry.id: entry for entry in self.laws}

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        raw = read(path)
        if not isinstance(raw.get("task"), str) or not raw["task"].strip():
            raise ManifestError("the manifest must declare a non-empty `task`")
        entries = raw.get("laws")
        if not isinstance(entries, list) or not entries:
            raise ManifestError("the manifest must declare a non-empty `laws` list")
        laws: list[LawEntry] = []
        for position, item in enumerate(entries, start=1):
            if not isinstance(item, dict):
                raise ManifestError(f"laws[{position}] is not a mapping")
            for field_name in ("id", "name"):
                if not isinstance(item.get(field_name), str) or not item[field_name]:
                    raise ManifestError(f"laws[{position}] has no `{field_name}`")
            laws.append(
                LawEntry(
                    id=item["id"],
                    name=item["name"],
                    law_class=str(item.get("class") or ""),
                    priority=item.get("priority"),
                    requirements=tuple(_as_list(item.get("requirements"))),
                    witness=item.get("witness"),
                    translation=item.get("translation") if isinstance(item.get("translation"), dict) else None,
                    raw=item,
                )
            )
        return cls(
            task=raw["task"],
            path=path,
            laws=tuple(laws),
            requirements=(
                tuple(_as_list(raw["requirements"])) if "requirements" in raw else None
            ),
            conformance_only=tuple(_as_list(raw.get("conformance_only_requirements"))),
            oracle_only=tuple(_as_list(raw.get("oracle_only_requirements"))),
            hashes=_hashes(raw),
            raw=raw,
        )


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _hashes(raw: Mapping[str, Any]) -> dict[str, str]:
    """Artifact hashes, from either `hashes:` or the single-file shorthand."""
    found: dict[str, str] = {}
    declared = raw.get("hashes")
    if isinstance(declared, dict):
        for key, value in declared.items():
            if isinstance(value, str) and value.strip():
                found[str(key)] = value.strip()
    single = raw.get("law_sha256")
    if isinstance(single, str) and single.strip():
        found.setdefault("LAWS.bend", single.strip())
    return found
