from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from codescent.engine.parsers.python import (
    LOW_CONFIDENCE,
    ParsedImport,
    ParsedPythonFile,
    ParsedReference,
    ParsedSymbol,
)

# Regex-heuristic Go pack — mirrors engine/packs_ts.py. There is NO tree-sitter
# (or any parser dependency) in this project; Go declarations are extracted with
# regexes and tagged LOW_CONFIDENCE because the parse is heuristic, not an AST.
GO_EXTENSIONS: Final = (".go",)

_PACKAGE_RE: Final[re.Pattern[str]] = re.compile(r"^\s*package\s+([A-Za-z_]\w*)")
_FUNC_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*[\(\[]",
)
_METHOD_RE: Final[re.Pattern[str]] = re.compile(r"^\s*func\s+\(")
_TYPE_RE: Final[re.Pattern[str]] = re.compile(r"^\s*type\s+([A-Za-z_]\w*)\b")
_SINGLE_IMPORT_RE: Final[re.Pattern[str]] = re.compile(
    r'^\s*import\s+(?:[A-Za-z_.]\w*\s+)?"([^"]+)"',
)
_IMPORT_OPEN_RE: Final[re.Pattern[str]] = re.compile(r"^\s*import\s*\(")
_IMPORT_MEMBER_RE: Final[re.Pattern[str]] = re.compile(
    r'^\s*(?:[A-Za-z_.]\w*\s+)?"([^"]+)"',
)
_CALL_RE: Final[re.Pattern[str]] = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
_CALL_KEYWORDS: Final = frozenset(
    {"func", "if", "for", "return", "switch", "go", "defer", "select", "range"},
)


@dataclass(frozen=True, slots=True)
class _Line:
    number: int
    text: str


def parse_go_file(path: Path | str, relative_path: str) -> ParsedPythonFile:
    module = _module_name(relative_path)
    try:
        raw = Path(path).read_text()
    except (OSError, UnicodeDecodeError) as error:
        # Degrade gracefully: unreadable/undecodable files yield an empty parse
        # with the error recorded, never an exception.
        return ParsedPythonFile(
            path=relative_path,
            module=module,
            is_test=_is_test_path(relative_path),
            symbols=(),
            imports=(),
            references=(),
            parse_error=str(error),
        )
    lines = tuple(
        _Line(number=index, text=text)
        for index, text in enumerate(raw.splitlines(), start=1)
    )
    package = _package_name(lines) or module
    return ParsedPythonFile(
        path=relative_path,
        module=package,
        is_test=_is_test_path(relative_path),
        symbols=_symbols(lines, package),
        imports=_imports(lines),
        references=_references(lines),
    )


def _symbols(lines: tuple[_Line, ...], module: str) -> tuple[ParsedSymbol, ...]:
    symbols: list[ParsedSymbol] = []
    for line in lines:
        symbol = _symbol_from_line(line, lines, module)
        if symbol is not None:
            symbols.append(symbol)
    return tuple(symbols)


def _symbol_from_line(
    line: _Line,
    lines: tuple[_Line, ...],
    module: str,
) -> ParsedSymbol | None:
    func = _FUNC_RE.match(line.text)
    if func is not None:
        name = func.group(1)
        kind = "method" if _METHOD_RE.match(line.text) else "function"
        return _symbol(name, module, kind, line, lines)
    type_match = _TYPE_RE.match(line.text)
    if type_match is not None:
        return _symbol(type_match.group(1), module, _type_kind(line.text), line, lines)
    return None


def _symbol(
    name: str,
    module: str,
    kind: str,
    line: _Line,
    lines: tuple[_Line, ...],
) -> ParsedSymbol:
    return ParsedSymbol(
        name=name,
        qualified_name=f"{module}.{name}",
        kind=kind,
        start_line=line.number,
        end_line=_symbol_end(lines, line.number),
        confidence=LOW_CONFIDENCE,
    )


def _imports(lines: tuple[_Line, ...]) -> tuple[ParsedImport, ...]:
    imports: list[ParsedImport] = []
    in_block = False
    for line in lines:
        if in_block:
            if ")" in line.text:
                in_block = False
                continue
            member = _IMPORT_MEMBER_RE.match(line.text)
            if member is not None:
                imports.append(_import(member.group(1), line.number))
            continue
        single = _SINGLE_IMPORT_RE.match(line.text)
        if single is not None:
            imports.append(_import(single.group(1), line.number))
        elif _IMPORT_OPEN_RE.match(line.text):
            in_block = True
    return tuple(imports)


def _import(module: str, line: int) -> ParsedImport:
    return ParsedImport(module=module, name=None, line=line, confidence=LOW_CONFIDENCE)


def _references(lines: tuple[_Line, ...]) -> tuple[ParsedReference, ...]:
    references: list[ParsedReference] = []
    for line in lines:
        for call in (match.group(1) for match in _CALL_RE.finditer(line.text)):
            if call in _CALL_KEYWORDS:
                continue
            references.append(
                ParsedReference(name=call, line=line.number, confidence=LOW_CONFIDENCE),
            )
    return tuple(references)


def _type_kind(text: str) -> str:
    if "struct" in text:
        return "struct"
    if "interface" in text:
        return "interface"
    return "type"


def _symbol_end(lines: tuple[_Line, ...], start: int) -> int:
    if "{" not in lines[start - 1].text:
        # Brace-less declarations (e.g. `type Id int`, single-line interfaces)
        # are one line long.
        return start
    depth = 0
    for line in lines[start - 1 :]:
        depth += line.text.count("{")
        depth -= line.text.count("}")
        if line.number > start and depth <= 0:
            return line.number
    return start


def _package_name(lines: tuple[_Line, ...]) -> str | None:
    for line in lines:
        match = _PACKAGE_RE.match(line.text)
        if match is not None:
            return match.group(1)
    return None


def _module_name(relative_path: str) -> str:
    without_suffix = relative_path.rsplit(".", maxsplit=1)[0]
    return ".".join(part for part in without_suffix.split("/") if part)


def _is_test_path(relative_path: str) -> bool:
    return relative_path.startswith("tests/") or relative_path.endswith("_test.go")
