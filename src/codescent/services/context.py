from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from codescent.core.paths import normalize_repo_path, resolve_repo_root
from codescent.engine.context import source_range
from codescent.services.symbols import SymbolService

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.engine.context.ranges import SourceRange
    from codescent.engine.parsers.python import ParsedPythonFile, ParsedSymbol

SOURCE_LINE_CAP = 8
LOW_CONFIDENCE_THRESHOLD = 0.6


class SymbolMatchPayload(TypedDict):
    name: str
    qualified_name: str
    path: str
    start_line: int
    end_line: int
    confidence: float


class FileContextPayload(TypedDict):
    path: str
    summary: str
    symbols: tuple[str, ...]
    imports: tuple[str, ...]
    likely_tests: tuple[str, ...]
    related_files: tuple[str, ...]
    source_ranges: tuple[dict[str, str | int], ...]
    risk_notes: tuple[str, ...]
    next_tools: tuple[str, ...]


class SymbolContextPayload(TypedDict):
    symbol: SymbolMatchPayload
    likely_tests: tuple[str, ...]
    source_ranges: tuple[dict[str, str | int], ...]
    risk_notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContextService:
    repo_root: Path | str

    def find_symbol(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> tuple[SymbolMatchPayload, ...]:
        files = SymbolService(self.repo_root).extract().files
        matches = [
            _symbol_payload(parsed, symbol)
            for parsed in files
            for symbol in parsed.symbols
            if _matches_symbol(query, symbol)
        ]
        return tuple(matches[: min(max(limit, 1), 20)])

    def get_file_context(self, path: str) -> FileContextPayload:
        repo_root = resolve_repo_root(self.repo_root)
        relative_path = (
            normalize_repo_path(repo_root, path).relative_to(repo_root).as_posix()
        )
        files = SymbolService(repo_root).extract().files
        parsed = _file_by_path(files, relative_path)
        ranges = _file_ranges(repo_root, parsed)
        likely_tests = _likely_tests(files, parsed)
        return {
            "path": parsed.path,
            "summary": _file_summary(parsed),
            "symbols": tuple(symbol.name for symbol in parsed.symbols),
            "imports": tuple(
                _import_text(imported.module, imported.name)
                for imported in parsed.imports
            ),
            "likely_tests": likely_tests,
            "related_files": likely_tests,
            "source_ranges": tuple(item.to_payload() for item in ranges),
            "risk_notes": _risk_notes(parsed),
            "next_tools": tuple(
                f"get_symbol_context:{symbol.qualified_name}"
                for symbol in parsed.symbols
            ),
        }

    def get_symbol_context(self, qualified_name: str) -> SymbolContextPayload:
        repo_root = resolve_repo_root(self.repo_root)
        files = SymbolService(repo_root).extract().files
        parsed, symbol = _find_qualified_symbol(files, qualified_name)
        return {
            "symbol": _symbol_payload(parsed, symbol),
            "likely_tests": _likely_tests(files, parsed, symbol.name),
            "source_ranges": (
                source_range(
                    repo_root,
                    parsed.path,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                    line_cap=SOURCE_LINE_CAP,
                ).to_payload(),
            ),
            "risk_notes": _risk_notes(parsed),
        }


def _symbol_payload(
    parsed: ParsedPythonFile,
    symbol: ParsedSymbol,
) -> SymbolMatchPayload:
    return {
        "name": symbol.name,
        "qualified_name": symbol.qualified_name,
        "path": parsed.path,
        "start_line": symbol.start_line,
        "end_line": symbol.end_line,
        "confidence": symbol.confidence,
    }


def _matches_symbol(query: str, symbol: ParsedSymbol) -> bool:
    folded_query = query.lower()
    return (
        folded_query in symbol.name.lower()
        or folded_query in symbol.qualified_name.lower()
    )


def _file_by_path(files: tuple[ParsedPythonFile, ...], path: str) -> ParsedPythonFile:
    return next(parsed for parsed in files if parsed.path == path)


def _find_qualified_symbol(
    files: tuple[ParsedPythonFile, ...],
    qualified_name: str,
) -> tuple[ParsedPythonFile, ParsedSymbol]:
    return next(
        (parsed, symbol)
        for parsed in files
        for symbol in parsed.symbols
        if symbol.qualified_name == qualified_name
    )


def _file_ranges(repo_root: Path, parsed: ParsedPythonFile) -> tuple[SourceRange, ...]:
    return tuple(
        source_range(
            repo_root,
            parsed.path,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            line_cap=SOURCE_LINE_CAP,
        )
        for symbol in parsed.symbols[:2]
    )


def _likely_tests(
    files: tuple[ParsedPythonFile, ...],
    parsed: ParsedPythonFile,
    symbol_name: str | None = None,
) -> tuple[str, ...]:
    candidates: list[str] = []
    module_tail = parsed.module.rsplit(".", maxsplit=1)[-1]
    for candidate in files:
        if not candidate.is_test:
            continue
        import_modules = {imported.module for imported in candidate.imports}
        reference_names = {reference.name for reference in candidate.references}
        if parsed.module in import_modules or module_tail in candidate.path:
            candidates.append(candidate.path)
            continue
        if symbol_name is not None and symbol_name in reference_names:
            candidates.append(candidate.path)
    return tuple(sorted(dict.fromkeys(candidates)))


def _file_summary(parsed: ParsedPythonFile) -> str:
    symbol_names = ", ".join(symbol.name for symbol in parsed.symbols) or "no symbols"
    return f"{parsed.path} defines {symbol_names}."


def _import_text(module: str, name: str | None) -> str:
    if name is None:
        return module
    return f"{module}:{name}"


def _risk_notes(parsed: ParsedPythonFile) -> tuple[str, ...]:
    notes: list[str] = []
    if parsed.parse_error is not None:
        notes.append(f"parse-error: {parsed.parse_error}")
    if any(
        reference.confidence < LOW_CONFIDENCE_THRESHOLD
        for reference in parsed.references
    ):
        notes.append("low-confidence references omitted from caller/callee claims")
    return tuple(notes)
