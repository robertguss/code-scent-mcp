"""Structural graph backend abstraction.

`GraphBackend` is a small read-only interface over the structural layer
(symbols, complexity props, call edges, clusters). The default and fallback
implementation, `NativeGraphBackend`, wraps CodeScent's own SQLite index and
changes no existing behaviour. An optional cbm-backed adapter lives in
``codescent.services.cbm_backend`` and degrades to this native backend whenever
cbm is absent or unhealthy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from codescent.services.symbols import ensure_symbols_indexed
from codescent.storage import RepositoryStorage

if TYPE_CHECKING:
    from pathlib import Path

# Languages cbm resolves with its Hybrid-LSP engine; only here is its CALL GRAPH
# trustworthy. For the tree-sitter tail cbm resolves by bare name and collapses
# every same-named symbol across languages, so its call edges / clusters for
# those languages must never reach CodeScent findings (see cbm_backend tiering).
HYBRID_LSP_LANGUAGES: frozenset[str] = frozenset(
    {
        "python",
        "typescript",
        "javascript",
        "go",
        "java",
        "rust",
        "csharp",
        "kotlin",
        "php",
        "c",
        "cpp",
    },
)


def is_hybrid_lsp(language: str) -> bool:
    """Return True when cbm's call graph is trustworthy for this language."""
    return language.lower() in HYBRID_LSP_LANGUAGES


@dataclass(frozen=True, slots=True)
class SymbolNode:
    qualified_name: str
    name: str
    kind: str
    path: str
    start_line: int
    end_line: int
    confidence: float
    language: str


@dataclass(frozen=True, slots=True)
class ComplexityProps:
    qualified_name: str
    path: str
    language: str
    line_span: int
    complexity: int


@dataclass(frozen=True, slots=True)
class CallEdge:
    caller_path: str
    callee_name: str
    start_line: int
    confidence: float
    language: str


@dataclass(frozen=True, slots=True)
class Cluster:
    cluster_id: str
    label: str
    members: tuple[str, ...]
    languages: tuple[str, ...]


@runtime_checkable
class GraphBackend(Protocol):
    """Read-only structural data source: symbols, complexity, edges, clusters."""

    def name(self) -> str: ...
    def available(self) -> bool: ...
    def symbols(self) -> tuple[SymbolNode, ...]: ...
    def complexity(self) -> tuple[ComplexityProps, ...]: ...
    def call_edges(self) -> tuple[CallEdge, ...]: ...
    def clusters(self) -> tuple[Cluster, ...]: ...


type _SymbolRow = tuple[str, str, str, str, int, int, float, str]
type _ReferenceRow = tuple[str, str, int, float, str]


def _directory_of(path: str) -> str:
    if "/" not in path:
        return "."
    return path.rsplit("/", maxsplit=1)[0]


@dataclass(frozen=True, slots=True)
class NativeGraphBackend:
    """Default backend: read-only over CodeScent's own SQLite index."""

    repo_root: Path | str

    def name(self) -> str:
        return "native"

    def available(self) -> bool:
        return True

    def symbols(self) -> tuple[SymbolNode, ...]:
        return tuple(
            SymbolNode(
                qualified_name=qualified_name,
                name=name,
                kind=kind,
                path=path,
                start_line=start_line,
                end_line=end_line,
                confidence=confidence,
                language=language,
            )
            for (
                qualified_name,
                name,
                kind,
                path,
                start_line,
                end_line,
                confidence,
                language,
            ) in self._symbol_rows()
        )

    def complexity(self) -> tuple[ComplexityProps, ...]:
        # ponytail: native has no cyclomatic metric; line span is the proxy.
        # cbm supplies a richer complexity when present. Upgrade: read a native
        # complexity column if the indexer ever computes one.
        return tuple(
            ComplexityProps(
                qualified_name=symbol.qualified_name,
                path=symbol.path,
                language=symbol.language,
                line_span=max(symbol.end_line - symbol.start_line + 1, 1),
                complexity=max(symbol.end_line - symbol.start_line + 1, 1),
            )
            for symbol in self.symbols()
        )

    def call_edges(self) -> tuple[CallEdge, ...]:
        return tuple(
            CallEdge(
                caller_path=caller_path,
                callee_name=callee_name,
                start_line=start_line,
                confidence=confidence,
                language=language,
            )
            for (
                caller_path,
                callee_name,
                start_line,
                confidence,
                language,
            ) in self._reference_rows()
        )

    def clusters(self) -> tuple[Cluster, ...]:
        # ponytail: directory grouping, not Leiden. cbm supplies real clusters.
        members_by_dir: dict[str, list[SymbolNode]] = {}
        for symbol in self.symbols():
            members_by_dir.setdefault(_directory_of(symbol.path), []).append(symbol)
        return tuple(
            Cluster(
                cluster_id=directory,
                label=f"dir:{directory}",
                members=tuple(sorted(item.qualified_name for item in members)),
                languages=tuple(sorted({item.language for item in members})),
            )
            for directory, members in sorted(members_by_dir.items())
        )

    def _symbol_rows(self) -> tuple[_SymbolRow, ...]:
        state = ensure_symbols_indexed(self.repo_root)
        with RepositoryStorage(state).read_connection() as connection:
            rows: list[_SymbolRow] = connection.execute(
                """
                select
                    symbols.qualified_name,
                    symbols.name,
                    symbols.kind,
                    files.path,
                    symbols.start_line,
                    symbols.end_line,
                    symbols.confidence,
                    files.language
                from symbols
                join files on files.id = symbols.file_id
                order by files.path, symbols.start_line, symbols.qualified_name
                """,
            ).fetchall()
        return tuple(rows)

    def _reference_rows(self) -> tuple[_ReferenceRow, ...]:
        state = ensure_symbols_indexed(self.repo_root)
        with RepositoryStorage(state).read_connection() as connection:
            rows: list[_ReferenceRow] = connection.execute(
                """
                select
                    files.path,
                    symbol_references.reference_text,
                    symbol_references.start_line,
                    symbol_references.confidence,
                    files.language
                from symbol_references
                join files on files.id = symbol_references.source_file_id
                order by
                    files.path,
                    symbol_references.start_line,
                    symbol_references.reference_text
                """,
            ).fetchall()
        return tuple(rows)
