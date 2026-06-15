from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from codescent.core.models import ProjectConfig
from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.engine.parsers.python import (
    ParsedPythonFile,
    ParsedSymbol,
    parse_python_file,
)
from codescent.engine.rules.model import CodeHealthFinding, FindingSpec, build_finding

if TYPE_CHECKING:
    from pathlib import Path

MODULE_LEVEL_KINDS: Final = frozenset({"class", "function", "async_function"})
ENTRYPOINT_NAMES: Final = frozenset({"main", "app", "run"})
MAX_DEAD_CODE_FINDINGS: Final = 200


@dataclass(frozen=True, slots=True)
class DeadCodeCandidate:
    path: str
    name: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class NameUseIndex:
    used_names: frozenset[str]
    candidates: tuple[DeadCodeCandidate, ...]


def build_name_use_index(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
) -> NameUseIndex:
    repo_root = resolve_repo_root(root)
    project_config = config or ProjectConfig()
    parsed_files: list[ParsedPythonFile] = []
    used_names: set[str] = set()

    for item in build_file_inventory(repo_root, config=project_config):
        if item.language != "python":
            continue
        parsed = parse_python_file(repo_root / item.path, item.path)
        parsed_files.append(parsed)
        used_names.update(reference.name for reference in parsed.references)
        used_names.update(imported.name for imported in parsed.imports if imported.name)
        used_names.update(_exported_names(repo_root / parsed.path))

    return NameUseIndex(
        used_names=frozenset(sorted(used_names)),
        candidates=tuple(_candidate_symbols(parsed_files, used_names)),
    )


def scan_dead_code(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
    limit: int = MAX_DEAD_CODE_FINDINGS,
) -> tuple[CodeHealthFinding, ...]:
    if limit < 1:
        return ()
    index = build_name_use_index(root, config=config)
    return tuple(
        _candidate_finding(candidate) for candidate in index.candidates[:limit]
    )


def _candidate_finding(candidate: DeadCodeCandidate) -> CodeHealthFinding:
    return build_finding(
        FindingSpec(
            rule_id="python.dead_code_candidate",
            title="Dead code candidate",
            message=(
                f"{candidate.qualified_name} is not referenced by the "
                "project-wide name-use index."
            ),
            file_path=candidate.path,
            symbol=candidate.qualified_name,
            severity="info",
            confidence=0.6,
            evidence={
                "start_line": candidate.start_line,
                "end_line": candidate.end_line,
                "kind": candidate.kind,
            },
            suggested_action=(
                "Verify no dynamic entrypoint or external caller depends on "
                "this symbol before removing it."
            ),
        ),
    )


def _candidate_symbols(
    parsed_files: list[ParsedPythonFile],
    used_names: set[str],
) -> list[DeadCodeCandidate]:
    candidates: list[DeadCodeCandidate] = []
    for parsed in parsed_files:
        if parsed.is_test:
            continue
        for symbol in parsed.symbols:
            if not _is_module_level_symbol(parsed, symbol):
                continue
            if _is_excluded_name(symbol.name):
                continue
            if symbol.name in used_names:
                continue
            candidates.append(
                DeadCodeCandidate(
                    path=parsed.path,
                    name=symbol.name,
                    qualified_name=symbol.qualified_name,
                    kind=symbol.kind,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                ),
            )
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.path,
            candidate.start_line,
            candidate.qualified_name,
        ),
    )


def _is_module_level_symbol(parsed: ParsedPythonFile, symbol: ParsedSymbol) -> bool:
    if symbol.kind not in MODULE_LEVEL_KINDS:
        return False
    expected = f"{parsed.module}.{symbol.name}" if parsed.module else f".{symbol.name}"
    return symbol.qualified_name == expected


def _is_excluded_name(name: str) -> bool:
    return name in ENTRYPOINT_NAMES or (name.startswith("__") and name.endswith("__"))


def _exported_names(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(), filename=path.as_posix())
    except (OSError, SyntaxError):
        return set()

    exported: set[str] = set()
    for node in tree.body:
        match node:
            case ast.Assign(targets=targets, value=value):
                if any(_is_all_target(target) for target in targets):
                    exported.update(_string_constants(value))
            case ast.AnnAssign(target=target, value=value):
                if value is not None and _is_all_target(target):
                    exported.update(_string_constants(value))
            case _:
                continue
    return exported


def _is_all_target(target: ast.AST) -> bool:
    return isinstance(target, ast.Name) and target.id == "__all__"


def _string_constants(node: ast.AST) -> set[str]:
    match node:
        case ast.List(elts=elts) | ast.Tuple(elts=elts) | ast.Set(elts=elts):
            return {
                element.value
                for element in elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
        case _:
            return set()
