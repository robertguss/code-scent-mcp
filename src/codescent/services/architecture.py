"""One-call architecture overview: languages, packages, layers, hotspots, modules.

A single BOUNDED orientation payload so an agent can skip many repo-map + read
cycles. De-facto modules come from cbm's clusters when a local cbm process is
present; otherwise a native label-propagation pass over the import graph derives
heuristic modules.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.engine.parsers.python import parse_python_file
from codescent.services.cbm_backend import select_graph_backend
from codescent.services.config import ConfigService

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from pathlib import Path

    from codescent.core.models import IndexedFile, ProjectConfig
    from codescent.engine.parsers.python import ParsedImport, ParsedPythonFile
    from codescent.services.cbm_backend import CbmClient
    from codescent.services.graph_backend import Cluster

MODULE_CAP: Final = 12
HOTSPOT_CAP: Final = 10
PACKAGE_CAP: Final = 20
LAYER_CAP: Final = 20
MEMBER_CAP: Final = 25
ENTRYPOINT_NAMES: Final = frozenset({"__main__.py", "cli.py", "main.py"})
WILDCARD_IMPORT: Final = "*"
_MAX_LP_ITERATIONS: Final = 10
_CBM_CONFIDENCE: Final = 0.9
_HEURISTIC_LINKED: Final = 0.6
_HEURISTIC_ISOLATED: Final = 0.3

ClusterSource = Literal["cbm", "heuristic"]


@dataclass(frozen=True, slots=True)
class ModuleView:
    name: str
    members: tuple[str, ...]
    size: int
    source: ClusterSource
    confidence: float


@dataclass(frozen=True, slots=True)
class Hotspot:
    path: str
    line_count: int


@dataclass(frozen=True, slots=True)
class Architecture:
    file_count: int
    languages: dict[str, int]
    packages: tuple[str, ...]
    entry_points: tuple[str, ...]
    layers: tuple[str, ...]
    hotspots: tuple[Hotspot, ...]
    modules: tuple[ModuleView, ...]
    cluster_source: ClusterSource


def build_architecture(
    repo: Path | str = ".",
    *,
    client: CbmClient | None = None,
    runner: Callable[[str], object] | None = None,
) -> Architecture:
    """Compose a single bounded architecture overview for ``repo``.

    When a healthy ``client`` (local cbm) is present its clusters become the
    de-facto modules; otherwise a native heuristic pass derives them.
    """
    repo_root = resolve_repo_root(repo)
    config = ConfigService(repo_root).load()
    inventory = build_file_inventory(repo_root, config=config)
    source_files = tuple(item for item in inventory if not item.is_test)
    backend = select_graph_backend(repo_root, client=client, runner=runner)
    if backend.name() == "cbm":
        modules = _cbm_modules(backend.clusters())
        cluster_source: ClusterSource = "cbm"
    else:
        modules = _heuristic_modules(repo_root, source_files)
        cluster_source = "heuristic"
    return Architecture(
        file_count=len(inventory),
        languages=_language_counts(inventory),
        packages=_packages(source_files),
        entry_points=_entry_points(source_files),
        layers=_layers(config, source_files),
        hotspots=_hotspots(source_files),
        modules=modules,
        cluster_source=cluster_source,
    )


def _language_counts(inventory: tuple[IndexedFile, ...]) -> dict[str, int]:
    counts: Counter[str] = Counter(item.language for item in inventory)
    return dict(sorted(counts.items()))


def _basename(path: str) -> str:
    return path.rsplit("/", maxsplit=1)[-1]


def _directory_of(path: str) -> str:
    if "/" not in path:
        return "."
    return path.rsplit("/", maxsplit=1)[0]


def _package_root(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if parts[:1] == ["src"]:
        parts = parts[1:]
    return parts[0] if parts else "."


def _packages(files: tuple[IndexedFile, ...]) -> tuple[str, ...]:
    roots = {_package_root(item.path) for item in files}
    return tuple(sorted(roots))[:PACKAGE_CAP]


def _layers(
    config: ProjectConfig,
    files: tuple[IndexedFile, ...],
) -> tuple[str, ...]:
    if config.architecture.rules:
        return tuple(sorted({rule.layer for rule in config.architecture.rules}))[
            :LAYER_CAP
        ]
    directories = sorted({_directory_of(item.path) for item in files})
    return tuple(directories)[:LAYER_CAP]


def _entry_points(files: tuple[IndexedFile, ...]) -> tuple[str, ...]:
    return tuple(
        item.path for item in files if _basename(item.path) in ENTRYPOINT_NAMES
    )


def _hotspots(files: tuple[IndexedFile, ...]) -> tuple[Hotspot, ...]:
    ranked = sorted(files, key=lambda item: (-item.line_count, item.path))
    return tuple(
        Hotspot(path=item.path, line_count=item.line_count)
        for item in ranked[:HOTSPOT_CAP]
    )


def _cbm_modules(clusters: tuple[Cluster, ...]) -> tuple[ModuleView, ...]:
    ranked = sorted(
        clusters,
        key=lambda cluster: (-len(cluster.members), cluster.label),
    )
    return tuple(
        ModuleView(
            name=cluster.label,
            members=tuple(cluster.members[:MEMBER_CAP]),
            size=len(cluster.members),
            source="cbm",
            confidence=_CBM_CONFIDENCE,
        )
        for cluster in ranked[:MODULE_CAP]
    )


def _heuristic_modules(
    repo_root: Path,
    files: tuple[IndexedFile, ...],
) -> tuple[ModuleView, ...]:
    paths = tuple(item.path for item in files if item.language == "python")
    adjacency = _import_graph(repo_root, paths)
    labels = _label_propagation(paths, adjacency)
    communities: dict[str, list[str]] = {}
    for path in paths:
        communities.setdefault(labels[path], []).append(path)
    ranked = sorted(communities.items(), key=lambda item: (-len(item[1]), item[0]))
    return tuple(
        _module_view(label, members, adjacency)
        for label, members in ranked[:MODULE_CAP]
    )


def _module_view(
    label: str,
    members: list[str],
    adjacency: Mapping[str, frozenset[str]],
) -> ModuleView:
    member_set = set(members)
    linked = any(adjacency[member] & member_set for member in members)
    confidence = _HEURISTIC_LINKED if linked else _HEURISTIC_ISOLATED
    return ModuleView(
        name=f"pkg:{label}",
        members=tuple(sorted(members))[:MEMBER_CAP],
        size=len(members),
        source="heuristic",
        confidence=confidence,
    )


def _import_graph(
    repo_root: Path,
    paths: tuple[str, ...],
) -> dict[str, frozenset[str]]:
    parsed = {path: parse_python_file(repo_root / path, path) for path in paths}
    module_map = _module_to_path(parsed.values())
    adjacency: dict[str, set[str]] = {path: set() for path in paths}
    for path, parsed_file in parsed.items():
        for imported in parsed_file.imports:
            target = _resolve_import(path, imported, module_map)
            if target is not None and target != path and target in adjacency:
                adjacency[path].add(target)
                adjacency[target].add(path)
    return {path: frozenset(targets) for path, targets in adjacency.items()}


def _module_to_path(parsed: Iterable[ParsedPythonFile]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for parsed_file in parsed:
        if parsed_file.module and parsed_file.module not in mapping:
            mapping[parsed_file.module] = parsed_file.path
    return mapping


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
    parts = [part for part in path.removesuffix(".py").split("/") if part]
    if parts[:1] == ["src"]:
        parts = parts[1:]
    return tuple(parts[:-1])


def _label_propagation(
    paths: tuple[str, ...],
    adjacency: Mapping[str, frozenset[str]],
) -> dict[str, str]:
    # ponytail: LP seeded by directory (a strong de-facto-module prior); import
    # edges then pull stray files into a neighbour's community. Pure
    # node-identity LP collapses to singletons on sparse import graphs.
    labels = {path: _directory_of(path) for path in paths}
    ordered = sorted(paths)
    for _ in range(_MAX_LP_ITERATIONS):
        changed = False
        for node in ordered:
            best = _dominant_label(labels, node, adjacency[node])
            if best != labels[node]:
                labels[node] = best
                changed = True
        if not changed:
            break
    return labels


def _dominant_label(
    labels: Mapping[str, str],
    node: str,
    neighbors: frozenset[str],
) -> str:
    counts: Counter[str] = Counter(labels[neighbor] for neighbor in neighbors)
    counts[labels[node]] += 1
    top = max(counts.values())
    return min(label for label, count in counts.items() if count == top)
