"""Root-cause clustering with effort/ROI for an executable improvement campaign.

Turns the flat finding backlog into a small set of themed clusters — e.g. "12
duplicate literals in src/codescent/mcp" rather than 12 separate to-dos — each
with a deterministic effort estimate, a health-gain estimate, and an ROI
(health-gain / effort). Clusters are ordered by ROI so the cheapest, highest-
impact work surfaces first. Pure transform over the existing findings; no new
indexing or network.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final

from codescent.core.models import FindingStatus
from codescent.services.findings import FindingsService

if TYPE_CHECKING:
    from codescent.storage.repositories import FindingRow

_ACTIONABLE_STATUSES: Final = frozenset(
    {
        FindingStatus.OPEN,
        FindingStatus.IN_PROGRESS,
        FindingStatus.NEEDS_REVIEW,
        FindingStatus.REGRESSED,
    },
)

# Base effort (in abstract points) to address a single finding of each rule, and
# how strongly additional findings in the same cluster add to that cost. A low
# cluster factor means fixing them together is cheap (the canonical "12 duplicate
# literals = one constants module"); ~1.0 means each finding is separate work.
_BASE_EFFORT: Final[dict[str, float]] = {
    "python.dead_code_candidate": 1.0,
    "python.duplicate_literal": 1.0,
    "python.todo_cluster": 2.0,
    "python.suspicious_slop_candidate": 2.0,
    "python.missing_nearby_test": 3.0,
    "python.changed_source_without_related_test": 3.0,
    "python.too_many_imports": 3.0,
    "python.deep_nesting": 5.0,
    "python.large_function": 5.0,
    "python.structural_near_duplicate": 5.0,
    "python.relative_large_function": 4.0,
    "python.relative_large_file": 6.0,
    "python.relative_large_class": 6.0,
    "python.large_file": 8.0,
    "python.large_class": 8.0,
    "python.mixed_responsibilities": 8.0,
}
_DEFAULT_BASE_EFFORT: Final = 3.0

# Rules where fixing the whole cluster together is much cheaper than one-by-one.
_CLUSTERABLE_RULES: Final = frozenset(
    {
        "python.dead_code_candidate",
        "python.duplicate_literal",
        "python.todo_cluster",
        "python.suspicious_slop_candidate",
        "python.missing_nearby_test",
        "python.changed_source_without_related_test",
        "python.too_many_imports",
    },
)
_CLUSTERABLE_FACTOR: Final = 0.2
_STRUCTURAL_FACTOR: Final = 0.8

_SEVERITY_WEIGHT: Final[dict[str, float]] = {"error": 3.0, "warning": 3.0, "info": 1.0}
_DEFAULT_SEVERITY_WEIGHT: Final = 1.0

_EFFORT_SMALL_MAX: Final = 4.0
_EFFORT_MEDIUM_MAX: Final = 12.0

_MEMBER_LIMIT: Final = 10

_THEME_TEMPLATES: Final[dict[str, str]] = {
    "python.duplicate_literal": "Consolidate {size} duplicate literal(s) in {scope}",
    "python.dead_code_candidate": "Remove {size} dead-code candidate(s) in {scope}",
    "python.missing_nearby_test": "Add nearby tests for {size} module(s) in {scope}",
    "python.changed_source_without_related_test": (
        "Add tests for {size} changed module(s) in {scope}"
    ),
    "python.too_many_imports": "Reduce imports in {size} module(s) in {scope}",
    "python.todo_cluster": "Resolve {size} TODO cluster(s) in {scope}",
    "python.large_function": "Break up {size} large function(s) in {scope}",
    "python.large_file": "Split {size} large file(s) in {scope}",
    "python.large_class": "Split {size} large class(es) in {scope}",
    "python.deep_nesting": "Flatten {size} deeply nested block(s) in {scope}",
    "python.structural_near_duplicate": (
        "Deduplicate {size} near-duplicate block(s) in {scope}"
    ),
    "python.relative_large_class": (
        "Review {size} class(es) large for this repo in {scope}"
    ),
}


@dataclass(frozen=True, slots=True)
class ImprovementCluster:
    theme: str
    rule_id: str
    scope: str
    size: int
    severity: str
    effort: str
    effort_points: float
    health_gain: float
    roi: float
    files: tuple[str, ...]
    finding_ids: tuple[str, ...]
    suggested_action: str


@dataclass(frozen=True, slots=True)
class ImprovementPlan:
    clusters: tuple[ImprovementCluster, ...]
    total_clusters: int
    total_findings: int


@dataclass(frozen=True, slots=True)
class ImprovementPlanService:
    repo_root: Path | str

    def get_improvement_plan(self) -> ImprovementPlan:
        findings = tuple(
            finding
            for finding in FindingsService(self.repo_root).get_smell_report().findings
            if finding.status in _ACTIONABLE_STATUSES
        )
        clusters = _build_clusters(findings)
        ordered = sorted(
            clusters,
            key=lambda cluster: (-cluster.roi, cluster.scope, cluster.rule_id),
        )
        return ImprovementPlan(
            clusters=tuple(ordered),
            total_clusters=len(ordered),
            total_findings=len(findings),
        )


def _build_clusters(findings: tuple[FindingRow, ...]) -> list[ImprovementCluster]:
    groups: dict[tuple[str, str], list[FindingRow]] = defaultdict(list)
    for finding in findings:
        groups[(finding.rule_id, _directory(finding.file_path))].append(finding)
    return [
        _cluster(rule_id, scope, members)
        for (rule_id, scope), members in groups.items()
    ]


def _cluster(
    rule_id: str,
    scope: str,
    members: list[FindingRow],
) -> ImprovementCluster:
    size = len(members)
    effort_points = _effort_points(rule_id, size)
    health_gain = round(
        sum(
            _severity_weight(member.severity) * member.confidence for member in members
        ),
        2,
    )
    roi = round(health_gain / effort_points, 3) if effort_points else 0.0
    files = tuple(sorted({member.file_path for member in members}))
    return ImprovementCluster(
        theme=_theme(rule_id, scope, size),
        rule_id=rule_id,
        scope=scope,
        size=size,
        severity=_max_severity(members),
        effort=_effort_bucket(effort_points),
        effort_points=round(effort_points, 2),
        health_gain=health_gain,
        roi=roi,
        # Keep the full membership: a cluster is the unit of work, so callers
        # must be able to reach every finding in it (the plan itself is bounded
        # at the cluster level). `files` is a capped human-facing summary.
        files=files[:_MEMBER_LIMIT],
        finding_ids=tuple(member.id for member in members),
        suggested_action=members[0].suggested_action,
    )


def _effort_points(rule_id: str, size: int) -> float:
    base = _BASE_EFFORT.get(rule_id, _DEFAULT_BASE_EFFORT)
    factor = (
        _CLUSTERABLE_FACTOR if rule_id in _CLUSTERABLE_RULES else _STRUCTURAL_FACTOR
    )
    return base * (1.0 + (size - 1) * factor)


def _effort_bucket(points: float) -> str:
    if points <= _EFFORT_SMALL_MAX:
        return "S"
    if points <= _EFFORT_MEDIUM_MAX:
        return "M"
    return "L"


def _severity_weight(severity: str) -> float:
    return _SEVERITY_WEIGHT.get(severity, _DEFAULT_SEVERITY_WEIGHT)


def _max_severity(members: list[FindingRow]) -> str:
    severities = {member.severity for member in members}
    if "error" in severities:
        return "error"
    if "warning" in severities:
        return "warning"
    return members[0].severity


def _theme(rule_id: str, scope: str, size: int) -> str:
    template = _THEME_TEMPLATES.get(
        rule_id,
        "Address {size} " + rule_id + " finding(s) in {scope}",
    )
    return template.format(size=size, scope=scope)


def _directory(file_path: str) -> str:
    return str(PurePosixPath(file_path).parent)
