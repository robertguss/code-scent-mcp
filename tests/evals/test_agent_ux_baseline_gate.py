"""Tests for the agent-experience regression gate (plan U8, R7)."""

from __future__ import annotations

import pytest

from codescent.evals.agent_ux.gate import find_regressions
from codescent.evals.agent_ux.models import AgentUxReport, DimensionResult


def _report(*dims: DimensionResult) -> AgentUxReport:
    return AgentUxReport(repo="x", surface_tool_count=48, dimensions=dims)


def _share(name: str, value: float) -> DimensionResult:
    return DimensionResult(name=name, value=value, unit="share")


def _tokens(name: str, value: float) -> DimensionResult:
    return DimensionResult(name=name, value=value, unit="tokens")


def test_identical_run_has_no_regressions() -> None:
    baseline = _report(_share("envelope", 0.7), _tokens("cost", 100.0))
    assert find_regressions(baseline, baseline) == []


def test_dropped_share_is_a_regression() -> None:
    baseline = _report(_share("envelope", 0.7))
    current = _report(_share("envelope", 0.6))
    regressions = find_regressions(current, baseline)
    assert len(regressions) == 1
    assert regressions[0]["reason"] == "regressed"


def test_risen_token_cost_is_a_regression() -> None:
    baseline = _report(_tokens("cost", 100.0))
    current = _report(_tokens("cost", 120.0))
    regressions = find_regressions(current, baseline)
    assert len(regressions) == 1
    assert regressions[0]["reason"] == "increased"


def test_improved_dimensions_do_not_regress() -> None:
    baseline = _report(_share("envelope", 0.7), _tokens("cost", 100.0))
    current = _report(_share("envelope", 0.9), _tokens("cost", 80.0))
    assert find_regressions(current, baseline) == []


def test_accuracy_dimension_is_advisory_and_never_gates() -> None:
    # R1 is reported but must not fail the gate even when it drops hard.
    baseline = _report(
        DimensionResult(name="tool_selection", value=0.5, unit="accuracy")
    )
    current = _report(
        DimensionResult(name="tool_selection", value=0.1, unit="accuracy")
    )
    assert find_regressions(current, baseline) == []


def test_vanished_dimension_is_a_regression() -> None:
    baseline = _report(_share("envelope", 0.7))
    current = _report()
    regressions = find_regressions(current, baseline)
    assert len(regressions) == 1
    assert regressions[0]["reason"] == "vanished"


def test_vanished_advisory_dimension_is_still_flagged() -> None:
    # A present accuracy dim never gates on value drift, but a *vanished* one is
    # structural -- so silently dropping R1 can't read as a pass.
    baseline = _report(
        DimensionResult(name="tool_selection", value=0.3, unit="accuracy")
    )
    regressions = find_regressions(_report(), baseline)
    assert len(regressions) == 1
    assert regressions[0]["reason"] == "vanished"


def test_unknown_unit_raises() -> None:
    # A typo'd unit must fail loudly, not fall silently to the wrong gate branch.
    baseline = _report(DimensionResult(name="weird", value=1.0, unit="furlongs"))
    with pytest.raises(ValueError, match="unknown unit"):
        _ = find_regressions(_report(), baseline)
