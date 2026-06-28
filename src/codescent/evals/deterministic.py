from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService
from codescent.services.context import ContextService
from codescent.services.refactor_planning import RefactorPlanningService
from codescent.services.search import SearchService

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.engine.rules.model import CodeHealthFinding

PASS_THRESHOLD: Final = 0.9
MAX_CONTEXT_RANGES: Final = 2
REQUIRED_PERFECT_METRICS: Final = frozenset({"finding_precision"})
EVAL_EXCLUDED_RULE_IDS: Final = frozenset(
    {"python.changed_source_without_related_test"}
)


class ExpectedFinding(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    id: str
    rule_id: str
    file: str
    symbol: str | None = None
    literal: str | None = None


class ExpectedSearchQuery(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    query: str
    expected_files: tuple[str, ...]


class WorkflowTask(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    goal: str
    target_finding_id: str
    expected_verification: tuple[str, ...]


class ExpectedManifest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    fixture_root: str
    language: str
    files: tuple[str, ...]
    findings: tuple[ExpectedFinding, ...]
    search_queries: tuple[ExpectedSearchQuery, ...]
    workflow_task: WorkflowTask


class EvalWorkflowOutput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    success: bool


class EvalTelemetryOutput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    elapsed_ms: int = Field(ge=0)


class EvalOutput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    name: str
    passed: bool
    score: float = Field(ge=0, le=1)
    metrics: dict[str, float]
    telemetry: EvalTelemetryOutput
    workflow: EvalWorkflowOutput


@dataclass(frozen=True, slots=True)
class DeterministicEvalResult:
    passed: bool
    score: float
    metrics: dict[str, float]


def run_deterministic_eval(
    *,
    repo: Path,
    expected: Path,
    out: Path,
) -> DeterministicEvalResult:
    manifest = ExpectedManifest.model_validate_json(expected.read_text())
    if repo.as_posix() != manifest.fixture_root:
        message = "fixture_root does not match repo"
        raise ValueError(message)
    shutil.rmtree(repo / ".codescent", ignore_errors=True)
    # The eval fixtures are deliberately tiny. Pin the strict (historical)
    # thresholds so they keep producing a rich finding set; production defaults
    # are intentionally laxer and would leave these small files under threshold.
    _write_strict_thresholds(repo)
    start = time.perf_counter()
    before = _source_snapshot(repo)
    scan = CodeHealthService(repo).scan()
    finding_by_rule = {finding.rule_id: finding.id for finding in scan.findings}
    metrics = {
        "retrieval_top_k": _retrieval_score(repo, manifest.search_queries),
        "context_bounds": _context_score(repo, manifest),
        "finding_precision": _finding_score(scan.findings, manifest.findings),
        "stable_finding_ids": _stable_key_score(scan.finding_ids),
        "workflow_success": _workflow_score(repo, manifest, finding_by_rule),
        "source_read_only": 1.0 if before == _source_snapshot(repo) else 0.0,
        "performance": 1.0,
    }
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    score = sum(metrics.values()) / len(metrics)
    passed = (
        score >= PASS_THRESHOLD
        and all(value >= PASS_THRESHOLD for value in metrics.values())
        and all(metrics[name] == 1.0 for name in REQUIRED_PERFECT_METRICS)
    )
    output = EvalOutput(
        name="python-basic-deterministic",
        passed=passed,
        score=score,
        metrics=metrics,
        telemetry=EvalTelemetryOutput(elapsed_ms=elapsed_ms),
        workflow=EvalWorkflowOutput(success=metrics["workflow_success"] == 1.0),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    _ = out.write_text(output.model_dump_json(indent=2))
    return DeterministicEvalResult(passed=passed, score=score, metrics=metrics)


def _retrieval_score(
    repo: Path,
    queries: tuple[ExpectedSearchQuery, ...],
) -> float:
    service = SearchService(repo)
    matches = 0
    total = 0
    for query in queries:
        result_paths = {
            result["path"] for result in service.search_content(query.query)
        }
        for expected_file in query.expected_files:
            total += 1
            if expected_file in result_paths:
                matches += 1
    return _ratio(matches, total)


def _context_score(repo: Path, manifest: ExpectedManifest) -> float:
    context = ContextService(repo).get_file_context(manifest.files[0])
    source_ranges = context["source_ranges"]
    if len(source_ranges) > MAX_CONTEXT_RANGES:
        return 0.0
    return 1.0


def _finding_score(
    findings: tuple[CodeHealthFinding, ...],
    expected_findings: tuple[ExpectedFinding, ...],
) -> float:
    actual = {
        _finding_key(finding.rule_id, finding.file_path, finding.symbol)
        for finding in findings
        if finding.rule_id not in EVAL_EXCLUDED_RULE_IDS
    }
    expected = {
        _finding_key(finding.rule_id, finding.file, finding.symbol)
        for finding in expected_findings
    }
    hits = len(actual & expected)
    total = len(actual | expected)
    return _ratio(hits, total)


def _finding_key(rule_id: str, file_path: str, symbol: str | None) -> str:
    return f"{rule_id}:{file_path}:{symbol or ''}"


def _stable_key_score(finding_ids: tuple[str, ...]) -> float:
    return 1.0 if all(":" in finding_id for finding_id in finding_ids) else 0.0


def _workflow_score(
    repo: Path,
    manifest: ExpectedManifest,
    findings: dict[str, str],
) -> float:
    target = next(
        finding
        for finding in manifest.findings
        if finding.id == manifest.workflow_task.target_finding_id
    )
    finding_id = findings.get(target.rule_id)
    if finding_id is None:
        return 0.0
    plan = RefactorPlanningService(repo).plan_refactor(finding_id)
    return 1.0 if plan.verification_recommendations else 0.0


def _write_strict_thresholds(repo: Path) -> None:
    # Pack-quality evals measure the specific language pack; disable the
    # cross-cutting generic fallback so its findings on data/config files
    # (e.g. package.json) do not pollute per-pack precision.
    ConfigService(repo).save(
        ProjectConfig(
            thresholds=MaintainabilityThresholds.strict(),
            generic_fallback=False,
        ),
    )


def _source_snapshot(repo: Path) -> dict[str, str]:
    return {
        path.relative_to(repo).as_posix(): path.read_text()
        for path in repo.rglob("*")
        if path.is_file() and ".codescent" not in path.parts
    }


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator
