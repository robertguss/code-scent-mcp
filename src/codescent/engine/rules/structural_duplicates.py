from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from codescent.core.models import ProjectConfig
from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.engine.rules.model import CodeHealthFinding, FindingSpec, build_finding
from codescent.engine.source_read import read_source_text

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

MAX_STRUCTURAL_CLUSTER_LOCATIONS: Final = 8
MAX_STRUCTURAL_LOCATION_EVIDENCE: Final = 4
MIN_STRUCTURAL_CLUSTER_MEMBERS: Final = 2
MIN_STRUCTURAL_NODES: Final = 18
MIN_STRUCTURAL_STATEMENTS: Final = 3
STRUCTURAL_FINGERPRINT_DIGEST_LENGTH: Final = 16

type StructuralKind = Literal["async_function", "class", "function"]
type StructuralNode = ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef


@dataclass(frozen=True, slots=True)
class StructuralFingerprint:
    name: str
    kind: StructuralKind
    fingerprint: str
    statement_count: int
    node_count: int
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class StructuralDuplicateLocation:
    path: str
    name: str
    kind: StructuralKind
    start_line: int
    end_line: int
    statement_count: int
    node_count: int


@dataclass(frozen=True, slots=True)
class StructuralDuplicateCluster:
    fingerprint: str
    member_count: int
    locations: tuple[StructuralDuplicateLocation, ...]


def group_structural_duplicates(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
) -> tuple[StructuralDuplicateCluster, ...]:
    repo_root = resolve_repo_root(root)
    project_config = config or ProjectConfig()
    counts: dict[str, int] = {}
    locations_by_fingerprint: dict[str, list[StructuralDuplicateLocation]] = {}

    for item in build_file_inventory(repo_root, config=project_config):
        if item.language != "python":
            continue
        source = read_source_text(repo_root / item.path)
        if source.text is None:
            continue
        for fingerprint in structural_fingerprints(source.text, filename=item.path):
            counts[fingerprint.fingerprint] = counts.get(fingerprint.fingerprint, 0) + 1
            locations = locations_by_fingerprint.setdefault(
                fingerprint.fingerprint,
                [],
            )
            if len(locations) < MAX_STRUCTURAL_CLUSTER_LOCATIONS:
                locations.append(
                    StructuralDuplicateLocation(
                        path=item.path,
                        name=fingerprint.name,
                        kind=fingerprint.kind,
                        start_line=fingerprint.start_line,
                        end_line=fingerprint.end_line,
                        statement_count=fingerprint.statement_count,
                        node_count=fingerprint.node_count,
                    ),
                )

    clusters: list[StructuralDuplicateCluster] = []
    for fingerprint, member_count in sorted(counts.items()):
        if member_count < MIN_STRUCTURAL_CLUSTER_MEMBERS:
            continue
        locations = tuple(
            sorted(
                locations_by_fingerprint[fingerprint],
                key=lambda location: (
                    location.path,
                    location.start_line,
                    location.name,
                ),
            ),
        )
        clusters.append(
            StructuralDuplicateCluster(
                fingerprint=fingerprint,
                member_count=member_count,
                locations=locations,
            ),
        )
    return tuple(clusters)


def structural_duplicate_findings(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
) -> tuple[CodeHealthFinding, ...]:
    return tuple(
        _cluster_finding(cluster)
        for cluster in group_structural_duplicates(root, config=config)
        if cluster.locations
    )


def structural_fingerprints(
    source_text: str,
    *,
    filename: str = "<unknown>",
) -> tuple[StructuralFingerprint, ...]:
    try:
        tree = ast.parse(source_text, filename=filename)
    except SyntaxError:
        return ()

    records: list[StructuralFingerprint] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef):
            continue
        fingerprint = structural_fingerprint(node)
        if fingerprint is None:
            continue
        records.append(fingerprint)
    return tuple(records)


def structural_fingerprint(node: StructuralNode) -> StructuralFingerprint | None:
    statement_count = _statement_count(node)
    node_count = sum(1 for _ in ast.walk(node))
    if statement_count < MIN_STRUCTURAL_STATEMENTS or node_count < MIN_STRUCTURAL_NODES:
        return None

    names = _NameNormalizer()
    fingerprint = _render(node, names)
    return StructuralFingerprint(
        name=node.name,
        kind=_kind(node),
        fingerprint=fingerprint,
        statement_count=statement_count,
        node_count=node_count,
        start_line=node.lineno,
        end_line=node.end_lineno or node.lineno,
    )


class _NameNormalizer:
    def __init__(self) -> None:
        self._names: dict[str, str] = {}

    def normalize(self, name: str) -> str:
        normalized = self._names.get(name)
        if normalized is None:
            normalized = f"name_{len(self._names)}"
            self._names[name] = normalized
        return normalized


def _render(node: ast.AST, names: _NameNormalizer) -> str:
    if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
        children = (node.args, *_body_without_docstring(node.body))
        token = _node_token(node, children, names)
    elif isinstance(node, ast.ClassDef):
        children = (*node.bases, *_body_without_docstring(node.body))
        token = _node_token(node, children, names)
    elif isinstance(node, ast.Name):
        token = f"Name({names.normalize(node.id)})"
    elif isinstance(node, ast.arg):
        token = f"arg({names.normalize(node.arg)})"
    elif isinstance(node, ast.Constant):
        token = f"Constant({_constant_kind(node.value)})"
    elif isinstance(node, ast.alias):
        token = f"alias({names.normalize(node.name)})"
    elif isinstance(node, ast.keyword):
        keyword = "*" if node.arg is None else names.normalize(node.arg)
        token = _node_token(node, (node.value,), names, prefix=f"keyword({keyword})")
    else:
        token = _node_token(node, ast.iter_child_nodes(node), names)
    return token


def _node_token(
    node: ast.AST,
    children: Iterable[ast.AST],
    names: _NameNormalizer,
    *,
    prefix: str | None = None,
) -> str:
    name = prefix or node.__class__.__name__
    child_tokens = ",".join(_render(child, names) for child in children)
    return f"{name}({child_tokens})"


def _body_without_docstring(body: list[ast.stmt]) -> tuple[ast.stmt, ...]:
    if not body:
        return ()
    first = body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return tuple(body[1:])
    return tuple(body)


def _constant_kind(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float | complex):
        return "number"
    if isinstance(value, str):
        return "str"
    if isinstance(value, bytes):
        return "bytes"
    return value.__class__.__name__


def _kind(node: StructuralNode) -> StructuralKind:
    if isinstance(node, ast.AsyncFunctionDef):
        return "async_function"
    if isinstance(node, ast.ClassDef):
        return "class"
    return "function"


def _statement_count(node: StructuralNode) -> int:
    return sum(1 for child in ast.walk(node) if isinstance(child, ast.stmt)) - 1


def _cluster_finding(cluster: StructuralDuplicateCluster) -> CodeHealthFinding:
    first = cluster.locations[0]
    return build_finding(
        FindingSpec(
            rule_id="python.structural_near_duplicate",
            title="Structural near-duplicate functions",
            message=(
                f"{first.path}:{first.start_line} shares a structural fingerprint "
                f"with {cluster.member_count - 1} other location(s)."
            ),
            file_path=first.path,
            symbol=first.name,
            severity="info",
            confidence=0.8,
            evidence={
                "count": cluster.member_count,
                "fingerprint": _fingerprint_digest(cluster.fingerprint),
                "locations": _locations_evidence(cluster),
            },
            suggested_action=(
                "Extract a shared helper or parameterize the duplicated logic."
            ),
        ),
    )


def _locations_evidence(cluster: StructuralDuplicateCluster) -> str:
    displayed = cluster.locations[:MAX_STRUCTURAL_LOCATION_EVIDENCE]
    parts = [
        f"{location.path}:{location.start_line}-{location.end_line}:{location.name}"
        for location in displayed
    ]
    hidden_count = cluster.member_count - len(displayed)
    if hidden_count > 0:
        parts.append(f"+{hidden_count} more")
    return "; ".join(parts)


def _fingerprint_digest(fingerprint: str) -> str:
    digest = hashlib.sha256(fingerprint.encode()).hexdigest()
    return f"sha256:{digest[:STRUCTURAL_FINGERPRINT_DIGEST_LENGTH]}"
