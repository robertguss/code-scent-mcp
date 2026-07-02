"""Severity/tier-gated default finding views (bead P3.1 / U1).

One default gate at the shared finding-view choke: the actionable set (warning+
severity OR verified tier) is the headline; the info+heuristic mass is a
bounded, opt-in tail. Presentation only -- finding_count and stored data are
untouched, and include_all / min_severity restore the full set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from codescent.core.errors import CodeScentError, ErrorCode
from codescent.core.models import (
    FindingStatus,
    MaintainabilityThresholds,
    ProjectConfig,
)
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService
from codescent.services.findings import (
    FindingsService,
    gate_findings,
    validate_min_severity,
)
from codescent.services.improvement_plan import ImprovementPlanService
from codescent.storage.repositories import FindingRow

if TYPE_CHECKING:
    from pathlib import Path


def _finding(
    *,
    finding_id: str,
    severity: str,
    tier: str = "heuristic",
    status: FindingStatus = FindingStatus.OPEN,
) -> FindingRow:
    return FindingRow(
        id=finding_id,
        stable_key=finding_id,
        rule_id="python.example",
        file_path="src/a.py",
        severity=severity,
        confidence=0.5,
        status=status,
        title="t",
        message="m",
        evidence_json="{}",
        suggested_action="a",
        events=(),
        confidence_tier=tier,
    )


def _is_actionable(finding: FindingRow) -> bool:
    return finding.severity != "info" or finding.confidence_tier == "verified"


# --------------------------------------------------------------------------- #
# Pure gate logic.
# --------------------------------------------------------------------------- #
def test_gate_headline_is_warning_or_verified() -> None:
    findings = (
        _finding(finding_id="w", severity="warning"),
        _finding(finding_id="vi", severity="info", tier="verified"),
        _finding(finding_id="hi", severity="info", tier="heuristic"),
    )
    gated = gate_findings(findings)
    assert {f.id for f in gated.headline} == {"w", "vi"}
    assert {f.id for f in gated.deferred} == {"hi"}
    assert gated.degraded is False


def test_gate_include_all_puts_everything_in_headline() -> None:
    findings = (_finding(finding_id="hi", severity="info"),)
    gated = gate_findings(findings, include_all=True)
    assert gated.headline == findings
    assert gated.deferred == ()
    assert gated.degraded is False


def test_gate_min_severity_info_admits_everything() -> None:
    findings = (_finding(finding_id="hi", severity="info"),)
    gated = gate_findings(findings, min_severity="info")
    assert {f.id for f in gated.headline} == {"hi"}
    assert gated.deferred == ()


def test_gate_degrades_when_nothing_actionable() -> None:
    # An info/heuristic-only repo must not be blanked out: the full set becomes
    # the headline with a degraded flag.
    findings = (
        _finding(finding_id="a", severity="info"),
        _finding(finding_id="b", severity="info"),
    )
    gated = gate_findings(findings)
    assert gated.headline == findings
    assert gated.deferred == ()
    assert gated.degraded is True


def test_validate_min_severity_rejects_unknown_recoverably() -> None:
    with pytest.raises(CodeScentError) as excinfo:
        _ = validate_min_severity("critical")
    error = excinfo.value
    assert error.code is ErrorCode.INVALID_VALUE
    valid_values = error.recovery["valid_values"]
    assert isinstance(valid_values, list)
    assert "info" in valid_values


# --------------------------------------------------------------------------- #
# Integration: the shared choke, exercised through the services.
# --------------------------------------------------------------------------- #
def _mixed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    package = repo / "src" / "pkg"
    package.mkdir(parents=True)
    # Duplicate literals -> info/heuristic findings (the deferred mass).
    for name in ("a", "b", "c"):
        _ = (package / f"{name}.py").write_text(
            'X = "dup-lit-value"\nY = "dup-lit-value"\nZ = "dup-lit-value"\n',
        )
    # A large function -> a warning finding (the actionable headline).
    body = "\n".join(f"    step_{index} = {index}" for index in range(40))
    _ = (package / "huge.py").write_text(f"def process() -> None:\n{body}\n")
    ConfigService(repo).save(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )
    return repo


def test_smell_report_headline_gates_info_tail_without_dropping(tmp_path: Path) -> None:
    repo = _mixed_repo(tmp_path)
    _ = CodeHealthService(repo).scan()
    service = FindingsService(repo)

    default = service.get_smell_report()
    full = service.get_smell_report(include_all=True)

    # finding_count unchanged: the gate partitions, never deletes.
    assert len(default.findings) == len(full.findings)
    assert len(default.headline) + len(default.deferred) == len(default.findings)
    # The gate defers a non-empty info/heuristic tail by default.
    assert default.deferred
    assert full.deferred == ()
    # Every headline entry is actionable; every deferred entry is info/heuristic.
    assert all(_is_actionable(f) for f in default.headline)
    assert all(not _is_actionable(f) for f in default.deferred)


def test_next_improvement_prefers_actionable_over_info(tmp_path: Path) -> None:
    repo = _mixed_repo(tmp_path)
    _ = CodeHealthService(repo).scan()

    finding = FindingsService(repo).get_next_improvement()

    assert finding is not None
    assert _is_actionable(finding)


def test_backlog_and_plan_inherit_the_same_gate(tmp_path: Path) -> None:
    repo = _mixed_repo(tmp_path)
    _ = CodeHealthService(repo).scan()

    backlog = FindingsService(repo).get_backlog()
    full_backlog = FindingsService(repo).get_backlog(include_all=True)
    by_id = {f.id: f for f in FindingsService(repo).get_smell_report().findings}
    # Backlog leads with an actionable finding (reordered, never dropped).
    assert set(backlog.finding_ids) == set(full_backlog.finding_ids)
    assert _is_actionable(by_id[backlog.finding_ids[0]])

    default_plan = ImprovementPlanService(repo).get_improvement_plan()
    full_plan = ImprovementPlanService(repo).get_improvement_plan(include_all=True)
    # The default plan gates out the info/heuristic firehose; include_all restores.
    assert full_plan.total_findings > default_plan.total_findings


def test_info_only_repo_still_surfaces_findings(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    package = repo / "src" / "pkg"
    package.mkdir(parents=True)
    # Duplicate literals only -> an info/heuristic-only repo.
    for name in ("a", "b"):
        _ = (package / f"{name}.py").write_text(
            'X = "only-info-value"\nY = "only-info-value"\nZ = "only-info-value"\n',
        )
    ConfigService(repo).save(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )
    _ = CodeHealthService(repo).scan()

    report = FindingsService(repo).get_smell_report()
    # The headline is never empty when findings exist: verified-tier info
    # findings stay actionable, and a fully-heuristic repo degrades to the full
    # set rather than hiding everything.
    assert report.findings
    assert report.headline
    assert FindingsService(repo).get_next_improvement() is not None
