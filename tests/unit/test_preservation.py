from __future__ import annotations

import pytest

from codescent.core.preservation import (
    PreservationCandidate,
    estimate_token_usage,
    rank_preservation_items,
)


@pytest.mark.parametrize(
    ("kind", "severity"),
    [
        ("error", "error"),
        ("traceback", "error"),
        ("failing_assertion", "error"),
        ("public_api", "info"),
        ("security_finding", "high"),
        ("highest_severity_finding", "critical"),
        ("circular_dependency", "warning"),
        ("unreadable_file", "error"),
        ("permission_error", "error"),
        ("environment_error", "error"),
        ("failed_command", "error"),
    ],
)
def test_critical_items_rank_before_ordinary_items(
    kind: str,
    severity: str,
) -> None:
    ranked = rank_preservation_items(
        [
            PreservationCandidate(
                kind="note",
                title="ordinary",
                message="ordinary content",
                content="ordinary content",
            ),
            PreservationCandidate(
                kind=kind,
                title=f"{kind} critical",
                message="important content",
                severity=severity,
                content="important content",
                source_range=(3, 9),
                snippet="important content",
            ),
        ],
    )

    assert ranked[0].kind == kind
    assert ranked[0].priority == 0
    assert ranked[0].preserve_reason
    assert ranked[1].kind == "note"
    assert ranked[1].priority > ranked[0].priority


def test_mixed_severity_findings_rank_high_before_low() -> None:
    ranked = rank_preservation_items(
        [
            PreservationCandidate(
                kind="finding",
                title="low",
                message="low severity finding",
                severity="low",
                content="low severity finding",
            ),
            PreservationCandidate(
                kind="finding",
                title="high",
                message="high severity finding",
                severity="high",
                content="high severity finding",
            ),
            PreservationCandidate(
                kind="note",
                title="ordinary",
                message="ordinary content",
                content="ordinary content",
            ),
        ],
    )

    assert [item.title for item in ranked[:2]] == ["high", "low"]
    assert ranked[0].priority < ranked[1].priority
    assert ranked[2].kind == "note"


def test_oversized_critical_content_remains_retrievable() -> None:
    critical_text = "Traceback (most recent call last):\n" + ("x" * 400)
    ranked = rank_preservation_items(
        [
            PreservationCandidate(
                kind="traceback",
                title="oversized traceback",
                message="stack trace",
                content=critical_text,
                source_range=(41, 88),
                snippet="Traceback (most recent call last):\n...",
            ),
        ],
        token_budget=10,
    )

    decision = ranked[0]
    assert decision.retrieval_required is True
    assert decision.warnings
    assert "retrieval_required" in decision.warnings[0]
    assert decision.source_range == (41, 88)
    assert decision.snippet == "Traceback (most recent call last):\n..."
    assert decision.token_estimate > 10
    assert decision.token_basis.startswith("ceil(utf-8-surrogatepass-bytes/4)")


def test_empty_input_and_surrogate_strings_are_handled_deterministically() -> None:
    empty_estimate = estimate_token_usage("")
    surrogate_text = "bad\udcfftext"
    surrogate_estimate = estimate_token_usage(surrogate_text)

    assert empty_estimate.tokens == 0
    assert empty_estimate.basis == "empty input"
    assert surrogate_estimate.tokens > 0
    assert "surrogatepass" in surrogate_estimate.basis
    assert rank_preservation_items([]) == ()
