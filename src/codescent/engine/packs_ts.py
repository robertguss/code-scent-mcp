from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from codescent.engine.parsers.python import (
    HIGH_CONFIDENCE,
    LOW_CONFIDENCE,
    ParsedImport,
    ParsedPythonFile,
    ParsedReference,
    ParsedSymbol,
)

TS_EXTENSIONS: Final = (".js", ".jsx", ".ts", ".tsx")
_IMPORT_RE: Final[re.Pattern[str]] = re.compile(
    r"""^\s*import\s+.+?\s+from\s+["']([^"']+)["']""",
)
_SIDE_EFFECT_IMPORT_RE: Final[re.Pattern[str]] = re.compile(
    r"""^\s*import\s+["']([^"']+)["']""",
)
_EXPORT_FUNCTION_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)",
)
_FUNCTION_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*function\s+([A-Za-z_$][\w$]*)",
)
_CLASS_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*export\s+(?:default\s+)?class\s+([A-Za-z_$][\w$]*)|^\s*class\s+([A-Za-z_$][\w$]*)",
)
_EXPORT_CONST_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*export\s+const\s+([A-Za-z_$][\w$]*)",
)
_CALL_RE: Final[re.Pattern[str]] = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")


@dataclass(frozen=True, slots=True)
class _Line:
    number: int
    text: str


def parse_typescript_file(path: Path | str, relative_path: str) -> ParsedPythonFile:
    lines = tuple(
        _Line(number=index, text=text)
        for index, text in enumerate(Path(path).read_text().splitlines(), start=1)
    )
    module = _module_name(relative_path)
    return ParsedPythonFile(
        path=relative_path,
        module=module,
        is_test=_is_test_path(relative_path),
        symbols=tuple(_symbols(lines, module, relative_path)),
        imports=tuple(_imports(lines)),
        references=tuple(_references(lines)),
    )


def _imports(lines: tuple[_Line, ...]) -> tuple[ParsedImport, ...]:
    imports: list[ParsedImport] = []
    for line in lines:
        module = _import_module(line.text)
        if module is not None:
            imports.append(
                ParsedImport(
                    module=module,
                    name=None,
                    line=line.number,
                    confidence=HIGH_CONFIDENCE,
                ),
            )
    return tuple(imports)


def _symbols(
    lines: tuple[_Line, ...],
    module: str,
    relative_path: str,
) -> tuple[ParsedSymbol, ...]:
    symbols: list[ParsedSymbol] = []
    for line in lines:
        name = _symbol_name(line.text)
        if name is None:
            continue
        kind = _symbol_kind(name=name, path=relative_path, text=line.text)
        symbols.append(
            ParsedSymbol(
                name=name,
                qualified_name=f"{module}.{name}",
                kind=kind,
                start_line=line.number,
                end_line=_symbol_end(lines, line.number),
                confidence=HIGH_CONFIDENCE,
            ),
        )
    return tuple(symbols)


def _references(lines: tuple[_Line, ...]) -> tuple[ParsedReference, ...]:
    references: list[ParsedReference] = []
    for line in lines:
        module = _import_module(line.text)
        if module is not None:
            references.append(
                ParsedReference(
                    name=module,
                    line=line.number,
                    confidence=HIGH_CONFIDENCE,
                ),
            )
        for call in tuple(match.group(1) for match in _CALL_RE.finditer(line.text)):
            if call in {"function", "if", "for", "return", "switch"}:
                continue
            references.append(
                ParsedReference(name=call, line=line.number, confidence=LOW_CONFIDENCE),
            )
    return tuple(references)


def _import_module(text: str) -> str | None:
    match = _IMPORT_RE.match(text) or _SIDE_EFFECT_IMPORT_RE.match(text)
    if match is None:
        return None
    return match.group(1)


def _symbol_name(text: str) -> str | None:
    for pattern in (_EXPORT_FUNCTION_RE, _FUNCTION_RE, _EXPORT_CONST_RE):
        match = pattern.match(text)
        if match is not None:
            return match.group(1)
    class_match = _CLASS_RE.match(text)
    if class_match is None:
        return None
    return class_match.group(1) or class_match.group(2)


def _symbol_kind(*, name: str, path: str, text: str) -> str:
    if path.endswith(("route.ts", "route.js")):
        return "route"
    if name.startswith("use"):
        return "hook"
    if _looks_like_component(name=name, path=path, text=text):
        return "component"
    if "class " in text:
        return "class"
    return "function"


def _looks_like_component(*, name: str, path: str, text: str) -> bool:
    return (
        name[:1].isupper()
        and path.endswith((".jsx", ".tsx"))
        and ("function" in text or "const" in text)
    )


def _symbol_end(lines: tuple[_Line, ...], start: int) -> int:
    depth = 0
    for line in lines[start - 1 :]:
        depth += line.text.count("{")
        depth -= line.text.count("}")
        if line.number > start and depth <= 0:
            return line.number
    return start


def _module_name(relative_path: str) -> str:
    without_suffix = relative_path.rsplit(".", maxsplit=1)[0]
    return ".".join(part for part in without_suffix.split("/") if part)


def _is_test_path(relative_path: str) -> bool:
    return relative_path.startswith("tests/") or ".test." in relative_path
