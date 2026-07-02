from pathlib import Path

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService
from codescent.services.improvement_plan import (
    ImprovementCluster,
    ImprovementPlanService,
)

STRICT_CONFIG = ProjectConfig(thresholds=MaintainabilityThresholds.strict())


def _duplicate_literal_module(name: str) -> str:
    literal = '"pending-review-status"'
    return (
        f"FIRST_{name} = {literal}\n"
        f"SECOND_{name} = {literal}\n"
        f"THIRD_{name} = {literal}\n"
    )


def _large_function_module() -> str:
    body = "\n".join(f"    step_{index} = {index}" for index in range(30))
    return f"def process() -> None:\n{body}\n"


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    pkg = repo / "src" / "pkg"
    pkg.mkdir(parents=True)
    # Five modules, each repeating a literal -> five duplicate_literal findings in
    # one directory: a single high-ROI cluster.
    for name in ("alpha", "beta", "gamma", "delta", "epsilon"):
        _ = (pkg / f"{name}.py").write_text(_duplicate_literal_module(name))
    # One large function -> a separate, lower-ROI structural cluster.
    _ = (pkg / "huge.py").write_text(_large_function_module())
    ConfigService(repo).save(STRICT_CONFIG)
    return repo


def _cluster(
    clusters: tuple[ImprovementCluster, ...],
    rule_id: str,
    scope: str,
) -> ImprovementCluster:
    return next(
        cluster
        for cluster in clusters
        if cluster.rule_id == rule_id and cluster.scope == scope
    )


def test_improvement_plan_clusters_by_theme_with_roi_and_effort(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _ = CodeHealthService(repo).scan()

    # include_all: duplicate_literal is info/heuristic and the default gate (U1)
    # would defer it; this test exercises the clustering/ROI logic over the full
    # finding set.
    plan = ImprovementPlanService(repo).get_improvement_plan(include_all=True)

    assert plan.total_clusters == len(plan.clusters)
    assert plan.total_findings > 0

    duplicates = _cluster(plan.clusters, "python.duplicate_literal", "src/pkg")
    large_function = _cluster(plan.clusters, "python.large_function", "src/pkg")

    assert duplicates.size == 5
    assert duplicates.theme == "Consolidate 5 duplicate literal(s) in src/pkg"
    assert duplicates.effort in {"S", "M"}
    assert len(duplicates.files) == 5
    # The full membership is retained (not capped), so every finding is reachable.
    assert len(duplicates.finding_ids) == duplicates.size
    # The clustered, mechanical fix has a higher ROI than the structural one.
    assert duplicates.roi > large_function.roi
    # Clusters are returned in descending ROI order.
    rois = [cluster.roi for cluster in plan.clusters]
    assert rois == sorted(rois, reverse=True)


def test_improvement_plan_is_deterministic(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _ = CodeHealthService(repo).scan()
    service = ImprovementPlanService(repo)

    first = service.get_improvement_plan()
    second = service.get_improvement_plan()

    assert first == second
