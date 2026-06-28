from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from codescent.core.models import ProjectConfig
from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.engine.parsers.python import (
    ParsedImport,
    ParsedPythonFile,
    parse_python_file,
)
from codescent.engine.rules.model import CodeHealthFinding, FindingSpec, build_finding

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

IMPORT_CYCLE_RULE_ID: Final = "python.import_cycle"
MAX_IMPORT_CYCLE_FINDINGS: Final = 100
MIN_CYCLE_SIZE: Final = 2
SELF_LOOP_SIZE: Final = 1
CYCLE_CONFIDENCE: Final = 0.9
SELF_LOOP_CONFIDENCE: Final = 0.7
WILDCARD_IMPORT: Final = "*"
_INIT_SUFFIXES: Final = ("__init__.py", "__init__.pyi")


def scan_import_cycles(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
    limit: int = MAX_IMPORT_CYCLE_FINDINGS,
) -> tuple[CodeHealthFinding, ...]:
    """Detect import cycles (dependency SCCs) over the resolved module graph.

    Builds a file-to-file import graph from the existing Python parser, computes
    strongly connected components (Tarjan), and emits one finding per cycle of
    size > 1 plus one per re-export self-loop. Unresolved (external) imports are
    skipped. Degrades to zero findings on empty or unparseable graphs.
    """
    if limit < 1:
        return ()
    repo_root = resolve_repo_root(root)
    project_config = config or ProjectConfig()
    parsed_files = _parse_python_files(repo_root, project_config)
    module_map = _module_to_path(parsed_files)
    graph, self_loops = _build_graph(parsed_files, module_map)
    return tuple(_findings_for_graph(graph, self_loops)[:limit])


def _parse_python_files(
    repo_root: Path,
    config: ProjectConfig,
) -> tuple[ParsedPythonFile, ...]:
    parsed: list[ParsedPythonFile] = []
    for item in build_file_inventory(repo_root, config=config):
        if item.language != "python" or item.is_test:
            continue
        parsed.append(parse_python_file(repo_root / item.path, item.path))
    return tuple(parsed)


def _module_to_path(parsed_files: tuple[ParsedPythonFile, ...]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    # Inventory is path-sorted, so first-wins keeps resolution deterministic.
    for parsed in parsed_files:
        key = _module_key(parsed.path)
        if key and key not in mapping:
            mapping[key] = parsed.path
    return mapping


def _build_graph(
    parsed_files: tuple[ParsedPythonFile, ...],
    module_map: Mapping[str, str],
) -> tuple[dict[str, frozenset[str]], frozenset[str]]:
    adjacency: dict[str, set[str]] = {parsed.path: set() for parsed in parsed_files}
    self_loops: set[str] = set()
    for parsed in parsed_files:
        for imported in parsed.imports:
            target = _resolve_import(parsed.path, imported, module_map)
            if target is None:
                continue
            if target == parsed.path:
                self_loops.add(parsed.path)
            elif target in adjacency:
                adjacency[parsed.path].add(target)
    graph = {source: frozenset(targets) for source, targets in adjacency.items()}
    return graph, frozenset(self_loops)


def _resolve_import(
    importer_path: str,
    imported: ParsedImport,
    module_map: Mapping[str, str],
) -> str | None:
    absolute = _absolute_module(importer_path, imported.module)
    if not absolute:
        return None
    if imported.name and imported.name != WILDCARD_IMPORT:
        submodule = f"{absolute}.{imported.name}"
        if submodule in module_map:
            return module_map[submodule]
    return module_map.get(absolute)


def _absolute_module(importer_path: str, raw_module: str) -> str:
    if not raw_module.startswith("."):
        return raw_module
    level = len(raw_module) - len(raw_module.lstrip("."))
    tail = raw_module[level:]
    package = _package_parts(importer_path)
    keep = len(package) - (level - 1)
    base = package[:keep] if keep >= 0 else ()
    parts = (*base, tail) if tail else base
    return ".".join(parts)


def _package_parts(path: str) -> tuple[str, ...]:
    parts = tuple(part for part in _module_key(path).split(".") if part)
    if path.endswith(_INIT_SUFFIXES):
        return parts
    return parts[:-1]


def _module_key(path: str) -> str:
    without_suffix = path.removesuffix(".py").removesuffix(".pyi")
    raw_parts = tuple(
        part for part in without_suffix.split("/") if part and part != "__init__"
    )
    parts = raw_parts[1:] if raw_parts[:1] == ("src",) else raw_parts
    return ".".join(parts)


def _findings_for_graph(
    graph: Mapping[str, frozenset[str]],
    self_loops: frozenset[str],
) -> list[CodeHealthFinding]:
    ranked: list[tuple[int, str, CodeHealthFinding]] = []
    for component in _strongly_connected_components(graph):
        if len(component) < MIN_CYCLE_SIZE:
            continue
        members = sorted(set(component))
        cycle = _representative_cycle(component, graph)
        ranked.append((len(members), members[0], _cycle_finding(cycle, members)))
    ranked.extend(
        (SELF_LOOP_SIZE, path, _self_loop_finding(path)) for path in sorted(self_loops)
    )
    # ponytail: rank by cycle size only. The churn signal lives in
    # services/git.py, which the engine layer must not import; "cycle size x
    # churn" degrades to size, per the spec's graceful-degradation allowance.
    ranked.sort(key=lambda entry: (-entry[0], entry[1]))
    return [finding for _size, _anchor, finding in ranked]


def _cycle_finding(
    cycle: tuple[str, ...],
    members: list[str],
) -> CodeHealthFinding:
    path_display = " -> ".join(cycle)
    from_file = cycle[-2]
    to_file = cycle[-1]
    return build_finding(
        FindingSpec(
            rule_id=IMPORT_CYCLE_RULE_ID,
            title="Import cycle",
            message=(f"{len(members)} modules form an import cycle: {path_display}."),
            file_path=members[0],
            symbol=None,
            severity="warning",
            confidence=CYCLE_CONFIDENCE,
            evidence={
                "cycle_path": path_display,
                "cycle_members": ", ".join(members),
                "cycle_size": len(members),
            },
            suggested_action=(
                # ponytail: "safest edge" = the back-edge that closes the
                # representative cycle; removing any one edge breaks the loop,
                # and naming a concrete edge is the actionable part.
                f"Break the cycle by decoupling the import from {from_file} to "
                f"{to_file}: move the shared definition into a separate module "
                "or use a local (function-scoped) import."
            ),
        ),
    )


def _self_loop_finding(path: str) -> CodeHealthFinding:
    return build_finding(
        FindingSpec(
            rule_id=IMPORT_CYCLE_RULE_ID,
            title="Self-referential import",
            message=f"{path} imports from itself, creating a re-export self-loop.",
            file_path=path,
            symbol=None,
            severity="warning",
            confidence=SELF_LOOP_CONFIDENCE,
            evidence={
                "cycle_path": f"{path} -> {path}",
                "cycle_members": path,
                "cycle_size": SELF_LOOP_SIZE,
            },
            suggested_action=(
                "Remove the self-referential import; re-export shared names "
                "from a separate module instead."
            ),
        ),
    )


def _representative_cycle(
    component: tuple[str, ...],
    graph: Mapping[str, frozenset[str]],
) -> tuple[str, ...]:
    members = frozenset(component)
    start = min(component)
    parents: dict[str, str | None] = {start: None}
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        for successor in sorted(graph[node]):
            if successor not in members or successor == node:
                continue
            if successor == start:
                return (*_path_to(parents, node), start)
            if successor not in parents:
                parents[successor] = node
                queue.append(successor)
    return (*sorted(component), min(component))


def _path_to(parents: Mapping[str, str | None], node: str) -> tuple[str, ...]:
    path: list[str] = []
    current: str | None = node
    while current is not None:
        path.append(current)
        current = parents[current]
    return tuple(reversed(path))


@dataclass(slots=True)
class _TarjanState:
    graph: Mapping[str, frozenset[str]]
    index: dict[str, int]
    lowlink: dict[str, int]
    on_stack: set[str]
    stack: list[str]
    components: list[tuple[str, ...]]
    counter: int


def _strongly_connected_components(
    graph: Mapping[str, frozenset[str]],
) -> list[tuple[str, ...]]:
    state = _TarjanState(
        graph=graph,
        index={},
        lowlink={},
        on_stack=set(),
        stack=[],
        components=[],
        counter=0,
    )
    for node in sorted(graph):
        if node not in state.index:
            _tarjan_visit(state, node)
    return state.components


def _tarjan_visit(state: _TarjanState, start: str) -> None:
    _open_node(state, start)
    work: list[tuple[str, Iterator[str]]] = [(start, iter(sorted(state.graph[start])))]
    while work:
        node, successors = work[-1]
        if _advance(state, node, successors, work):
            continue
        _ = work.pop()
        _finalize_node(state, node, work)


def _advance(
    state: _TarjanState,
    node: str,
    successors: Iterator[str],
    work: list[tuple[str, Iterator[str]]],
) -> bool:
    for successor in successors:
        if successor == node:
            continue
        if successor not in state.index:
            _open_node(state, successor)
            work.append((successor, iter(sorted(state.graph[successor]))))
            return True
        if successor in state.on_stack:
            state.lowlink[node] = min(state.lowlink[node], state.index[successor])
    return False


def _open_node(state: _TarjanState, node: str) -> None:
    state.index[node] = state.counter
    state.lowlink[node] = state.counter
    state.counter += 1
    state.stack.append(node)
    state.on_stack.add(node)


def _finalize_node(
    state: _TarjanState,
    node: str,
    work: list[tuple[str, Iterator[str]]],
) -> None:
    if state.lowlink[node] == state.index[node]:
        state.components.append(_pop_component(state, node))
    if work:
        parent = work[-1][0]
        state.lowlink[parent] = min(state.lowlink[parent], state.lowlink[node])


def _pop_component(state: _TarjanState, root: str) -> tuple[str, ...]:
    component: list[str] = []
    while True:
        member = state.stack.pop()
        state.on_stack.discard(member)
        component.append(member)
        if member == root:
            break
    return tuple(component)
