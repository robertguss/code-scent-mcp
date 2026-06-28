from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from codescent.services.refactor_planning import (
    FindingContext,
    ImpactReport,
    RefactorPlanningService,
    SafeRefactorPlan,
)
from codescent.services.refactor_preflight import (
    RefactorPreflightBundle,
    RefactorPreflightService,
)
from codescent.services.verification import VerificationService
from codescent.services.verify_refactor import VerifyRefactorService

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from codescent.services.risk import ChangedFileHealth, RiskFinding
    from codescent.services.verification import (
        SelectedTests,
        SuggestedTests,
        VerificationRecommendation,
    )
    from codescent.services.verify_refactor import VerifyResult


class FindingContextToolPayload(TypedDict):
    ok: bool
    finding_id: str
    rule_id: str
    summary: str
    affected_files: tuple[str, ...]
    relevant_symbols: tuple[str, ...]
    relevant_tests: tuple[str, ...]
    source_ranges: tuple[dict[str, str | int], ...]
    risk_notes: tuple[str, ...]
    suggested_action: str
    next_tools: tuple[str, ...]


class RefactorPlanToolPayload(TypedDict):
    ok: bool
    finding_id: str
    goal: str
    non_goals: tuple[str, ...]
    affected_files: tuple[str, ...]
    relevant_symbols: tuple[str, ...]
    risk: str
    steps: tuple[str, ...]
    fallback: str
    expected_behavior_preservation: tuple[str, ...]
    verification_recommendations: tuple[str, ...]


class SuggestedTestsToolPayload(TypedDict):
    ok: bool
    commands: tuple[str, ...]
    likely_tests: tuple[str, ...]
    executes_in_v1: bool


class SelectTestsToolPayload(TypedDict):
    ok: bool
    changed_files: tuple[str, ...]
    test_files: tuple[str, ...]
    command: str
    executes_in_v1: bool


class VerifyChangeToolPayload(TypedDict):
    ok: bool
    executes: bool
    recommendation_id: int
    recommended_commands: tuple[str, ...]
    likely_tests: tuple[str, ...]
    missing_characterization_tests: tuple[str, ...]


class ImpactToolPayload(TypedDict):
    ok: bool
    target_type: str
    target: str
    affected_files: tuple[str, ...]
    likely_tests: tuple[str, ...]
    risk_notes: tuple[str, ...]
    confidence: float


class CoChangeEntryPayload(TypedDict):
    path: str
    commits: int


# Mirrors risk_tools' changed-file-health payload so the preflight section is
# byte-identical to get_changed_file_health; kept local to avoid importing a
# sibling tool module's types at runtime for schema generation.
class PreflightRiskFindingPayload(TypedDict):
    finding_id: str
    rule_id: str
    file_path: str
    severity: str
    confidence: float
    status: str


class PreflightChangedFileHealthPayload(TypedDict):
    ok: bool
    path: str
    risk_score: float
    risk_level: str
    finding_ids: tuple[str, ...]
    findings: tuple[PreflightRiskFindingPayload, ...]
    suggested_tests: tuple[str, ...]
    recommended_commands: tuple[str, ...]
    risk_notes: tuple[str, ...]


class RefactorPreflightToolPayload(TypedDict):
    ok: bool
    target_type: str
    target: str
    file_path: str
    impact: ImpactToolPayload
    co_change: tuple[CoChangeEntryPayload, ...]
    test_selection: SelectTestsToolPayload
    changed_file_health: PreflightChangedFileHealthPayload
    warnings: tuple[str, ...]
    next_tools: tuple[str, ...]


class VerifyRefactorToolPayload(TypedDict):
    ok: bool
    verifiable: bool
    preserved: bool
    path: str
    base_ref: str
    transform_kind: str
    language: str
    violations: tuple[dict[str, str], ...]
    warnings: tuple[str, ...]
    added_symbols: tuple[str, ...]
    removed_symbols: tuple[str, ...]
    changed_symbols: tuple[str, ...]
    confidence: float
    next_tools: tuple[str, ...]


def register_planning_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Use CodeScent to retrieve bounded finding context before reading "
            "whole files. This tool is read-only for source files."
        ),
    )(get_finding_context)
    _ = mcp.tool(
        description=(
            "Use CodeScent to produce a safe refactor plan with non-goals, "
            "risks, fallback, and verification recommendations."
        ),
    )(plan_refactor)
    _ = mcp.tool(
        description=(
            "Use CodeScent to recommend likely tests and commands. This tool "
            "does not execute target project tests in V1."
        ),
    )(suggest_tests)
    _ = mcp.tool(
        description=(
            "Use CodeScent to compute the bounded minimal test set for the "
            "current changes or given paths and a single focused command. "
            "Recommend-only; does not execute target project tests."
        ),
    )(select_tests)
    _ = mcp.tool(
        description=(
            "Use CodeScent to estimate local blast radius for a file, symbol, "
            "or finding with bounded confidence-labeled evidence."
        ),
    )(get_impact)
    _ = mcp.tool(
        description=(
            "Use CodeScent to record recommend-only verification commands. "
            "This does not execute target project commands."
        ),
    )(verify_change)
    _ = mcp.tool(
        description=(
            "Use CodeScent to deterministically check that an edit preserved a "
            "Python file's public surface (exported symbols and signatures) "
            "versus a git ref. Read-only; proves behavior preservation or "
            "reports concrete violations."
        ),
    )(verify_refactor)
    _ = mcp.tool(
        description=(
            "Use CodeScent to run a one-call refactor preflight before an edit: "
            "a bounded, deduped blast-radius bundle that composes impact "
            "(callers/refs), git co-change coupling, the minimal verification "
            "test set, and changed-file health for a file, symbol, or finding. "
            "Pure composition of existing analyses; read-only for source files."
        ),
    )(refactor_preflight)


def get_finding_context(
    finding_id: str,
    repo: str = ".",
) -> FindingContextToolPayload:
    return _context_payload(
        RefactorPlanningService(repo).get_finding_context(finding_id),
    )


def plan_refactor(
    finding_id: str,
    repo: str = ".",
) -> RefactorPlanToolPayload:
    return _plan_payload(RefactorPlanningService(repo).plan_refactor(finding_id))


def suggest_tests(
    finding_id: str,
    repo: str = ".",
) -> SuggestedTestsToolPayload:
    return _tests_payload(RefactorPlanningService(repo).suggest_tests(finding_id))


def select_tests(
    repo: str = ".",
    paths: tuple[str, ...] | None = None,
) -> SelectTestsToolPayload:
    return _select_tests_payload(
        VerificationService(repo).select_tests(paths=paths),
    )


def get_impact(
    repo: str = ".",
    target: str | None = None,
    target_type: str = "file",
    finding_id: str | None = None,
) -> ImpactToolPayload:
    return _impact_payload(
        RefactorPlanningService(repo).get_impact(
            target=target,
            target_type=target_type,
            finding_id=finding_id,
        ),
    )


def verify_refactor(
    path: str,
    repo: str = ".",
    base_ref: str = "HEAD",
    transform_kind: str = "generic",
) -> VerifyRefactorToolPayload:
    result = VerifyRefactorService(repo).verify_refactor(
        path=path,
        base_ref=base_ref,
        transform_kind=transform_kind,
    )
    return _verify_refactor_payload(result)


def verify_change(finding_id: str, repo: str = ".") -> VerifyChangeToolPayload:
    return _verify_change_payload(
        RefactorPlanningService(repo).verify_change(finding_id),
    )


def refactor_preflight(
    repo: str = ".",
    target: str | None = None,
    target_type: str = "file",
    finding_id: str | None = None,
) -> RefactorPreflightToolPayload:
    return _preflight_payload(
        RefactorPreflightService(repo).preflight(
            target=target,
            target_type=target_type,
            finding_id=finding_id,
        ),
    )


def _context_payload(context: FindingContext) -> FindingContextToolPayload:
    return {
        "ok": True,
        "finding_id": context.finding_id,
        "rule_id": context.rule_id,
        "summary": context.summary,
        "affected_files": context.affected_files,
        "relevant_symbols": context.relevant_symbols,
        "relevant_tests": context.relevant_tests,
        "source_ranges": context.source_ranges,
        "risk_notes": context.risk_notes,
        "suggested_action": context.suggested_action,
        "next_tools": context.next_tools,
    }


def _plan_payload(plan: SafeRefactorPlan) -> RefactorPlanToolPayload:
    return {
        "ok": True,
        "finding_id": plan.finding_id,
        "goal": plan.goal,
        "non_goals": plan.non_goals,
        "affected_files": plan.affected_files,
        "relevant_symbols": plan.relevant_symbols,
        "risk": plan.risk,
        "steps": plan.steps,
        "fallback": plan.fallback,
        "expected_behavior_preservation": plan.expected_behavior_preservation,
        "verification_recommendations": plan.verification_recommendations,
    }


def _tests_payload(suggested: SuggestedTests) -> SuggestedTestsToolPayload:
    return {
        "ok": True,
        "commands": suggested.commands,
        "likely_tests": suggested.likely_tests,
        "executes_in_v1": suggested.executes_in_v1,
    }


def _select_tests_payload(selected: SelectedTests) -> SelectTestsToolPayload:
    return {
        "ok": True,
        "changed_files": selected.changed_files,
        "test_files": selected.test_files,
        "command": selected.command,
        "executes_in_v1": selected.executes_in_v1,
    }


def _impact_payload(impact: ImpactReport) -> ImpactToolPayload:
    return {
        "ok": True,
        "target_type": impact.target_type,
        "target": impact.target,
        "affected_files": impact.affected_files,
        "likely_tests": impact.likely_tests,
        "risk_notes": impact.risk_notes,
        "confidence": impact.confidence,
    }


def _preflight_payload(
    bundle: RefactorPreflightBundle,
) -> RefactorPreflightToolPayload:
    return {
        "ok": bundle.ok,
        "target_type": bundle.target_type,
        "target": bundle.target,
        "file_path": bundle.file_path,
        "impact": _impact_payload(bundle.impact),
        "co_change": tuple(
            {"path": entry.path, "commits": entry.commits} for entry in bundle.co_change
        ),
        "test_selection": _select_tests_payload(bundle.test_selection),
        "changed_file_health": _changed_file_health_payload(
            bundle.changed_file_health,
        ),
        "warnings": bundle.warnings,
        "next_tools": bundle.next_tools,
    }


def _changed_file_health_payload(
    health: ChangedFileHealth,
) -> PreflightChangedFileHealthPayload:
    return {
        "ok": health.ok,
        "path": health.path,
        "risk_score": health.risk_score,
        "risk_level": health.risk_level,
        "finding_ids": tuple(finding.finding_id for finding in health.findings),
        "findings": tuple(
            _risk_finding_payload(finding) for finding in health.findings
        ),
        "suggested_tests": health.suggested_tests,
        "recommended_commands": health.recommended_commands,
        "risk_notes": health.risk_notes,
    }


def _risk_finding_payload(finding: RiskFinding) -> PreflightRiskFindingPayload:
    return {
        "finding_id": finding.finding_id,
        "rule_id": finding.rule_id,
        "file_path": finding.file_path,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "status": finding.status,
    }


def _verify_change_payload(
    recommendation: VerificationRecommendation,
) -> VerifyChangeToolPayload:
    return {
        "ok": True,
        "executes": recommendation.executes,
        "recommendation_id": recommendation.recommendation_id,
        "recommended_commands": recommendation.recommended_commands,
        "likely_tests": recommendation.likely_tests,
        "missing_characterization_tests": (
            recommendation.missing_characterization_tests
        ),
    }


def _verify_refactor_payload(result: VerifyResult) -> VerifyRefactorToolPayload:
    return {
        "ok": True,
        "verifiable": result.verifiable,
        "preserved": result.preserved,
        "path": result.path,
        "base_ref": result.base_ref,
        "transform_kind": result.transform_kind,
        "language": result.language,
        "violations": tuple(
            {
                "kind": violation.kind,
                "symbol": violation.symbol,
                "detail": violation.detail,
            }
            for violation in result.violations
        ),
        "warnings": result.warnings,
        "added_symbols": result.added_symbols,
        "removed_symbols": result.removed_symbols,
        "changed_symbols": result.changed_symbols,
        "confidence": result.confidence,
        "next_tools": ("get_finding_context", "suggest_tests", "rescan"),
    }
