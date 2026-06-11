from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from codescent.services.refactor_planning import (
    FindingContext,
    ImpactReport,
    RefactorPlanningService,
    SafeRefactorPlan,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from codescent.services.verification import SuggestedTests


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


class ImpactToolPayload(TypedDict):
    ok: bool
    target_type: str
    target: str
    affected_files: tuple[str, ...]
    likely_tests: tuple[str, ...]
    risk_notes: tuple[str, ...]
    confidence: float


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
            "Use CodeScent to estimate local blast radius for a file, symbol, "
            "or finding with bounded confidence-labeled evidence."
        ),
    )(get_impact)


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
