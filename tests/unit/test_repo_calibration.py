"""Per-repo severity calibration (noise normalization) — unit tests.

Covers the deterministic baseline-noise model in ``services.calibration`` and its
integration into ``services.risk.rank_findings``: a rule that fires everywhere is
down-weighted, a rare rule is preserved, nothing is hidden, and the existing
severity/tier ranking behavior is unchanged when no weights are supplied.
"""

from codescent.core.models import AdaptiveSettings, FindingStatus
from codescent.engine.rules.model import (
    CONFIDENCE_TIER_HEURISTIC,
    CONFIDENCE_TIER_VERIFIED,
)
from codescent.services.calibration import (
    NoiseBaselineReport,
    RuleNoiseBaseline,
    _noise_baseline,  # pyright: ignore[reportPrivateUsage]
)
from codescent.services.risk import RiskFinding, rank_findings
from codescent.storage.repositories import FindingRow

SETTINGS = AdaptiveSettings()


def _finding(rule_id: str, *, file_path: str) -> FindingRow:
    return FindingRow(
        id=f"{rule_id}:{file_path}",
        stable_key=f"{rule_id}:{file_path}",
        rule_id=rule_id,
        file_path=file_path,
        severity="warning",
        confidence=0.8,
        status=FindingStatus.OPEN,
        title="t",
        message="m",
        evidence_json="{}",
        suggested_action="a",
        events=(),
    )


def _noisy_then_rare(
    settings: AdaptiveSettings = SETTINGS,
) -> tuple[NoiseBaselineReport, RuleNoiseBaseline, RuleNoiseBaseline]:
    findings = (
        *(_finding("noisy.rule", file_path=f"src/pkg/n{i}.py") for i in range(9)),
        _finding("rare.rule", file_path="src/pkg/rare.py"),
    )
    report = _noise_baseline(findings, settings)
    weights = {rule.rule_id: rule for rule in report.rules}
    return report, weights["noisy.rule"], weights["rare.rule"]


def test_noisy_rule_downweighted_rare_rule_preserved() -> None:
    report, noisy, rare = _noisy_then_rare()

    assert report.normalized is True
    assert report.total_findings == 10
    # The rule firing everywhere is down-weighted below the rare one.
    assert noisy.noise_weight < rare.noise_weight
    # The rare rule stays close to full weight (stands out).
    assert rare.noise_weight >= 0.97
    # Bounded to [floor, 1.0].
    assert SETTINGS.confidence_floor <= noisy.noise_weight <= 1.0


def test_cold_start_below_min_sample_leaves_weights_unchanged() -> None:
    findings = tuple(
        _finding("noisy.rule", file_path=f"src/pkg/n{i}.py") for i in range(5)
    )

    report = _noise_baseline(findings, SETTINGS)

    assert report.normalized is False
    assert all(rule.noise_weight == 1.0 for rule in report.rules)


def test_baseline_is_deterministic_and_order_independent() -> None:
    report_a, _, _ = _noisy_then_rare()
    # Re-derive from the same findings in reverse order: counts are independent of
    # iteration order, so the baseline round-trips identically.
    findings = (
        _finding("rare.rule", file_path="src/pkg/rare.py"),
        *(_finding("noisy.rule", file_path=f"src/pkg/n{i}.py") for i in range(9)),
    )
    report_b = _noise_baseline(findings, SETTINGS)

    assert report_a == report_b


def test_noise_weight_respects_floor() -> None:
    settings = AdaptiveSettings(max_confidence_delta=1.0, confidence_floor=0.3)
    # A single rule = 100% firing rate -> 1 - 1.0*1.0 = 0, clamped up to the floor.
    findings = tuple(
        _finding("noisy.rule", file_path=f"src/pkg/n{i}.py") for i in range(8)
    )

    report = _noise_baseline(findings, settings)

    assert report.rules[0].firing_rate == 1.0
    assert report.rules[0].noise_weight == settings.confidence_floor


def test_nothing_hidden_every_rule_and_finding_accounted_for() -> None:
    report, _, _ = _noisy_then_rare()

    # Transparent: every rule appears with a positive count and the counts sum to
    # the total findings — normalization re-ranks, it never drops a finding.
    assert sum(rule.firing_count for rule in report.rules) == report.total_findings
    assert all(rule.firing_count > 0 for rule in report.rules)


def _risk(rule_id: str, *, tier: str, severity: str = "warning") -> RiskFinding:
    return RiskFinding(
        finding_id=f"{severity}:{tier}:{rule_id}",
        rule_id=rule_id,
        file_path="src/pkg/a.py",
        severity=severity,
        confidence=0.9,
        confidence_tier=tier,
        status="open",
    )


def test_rank_findings_weights_sink_noisy_rule() -> None:
    noisy = _risk("noisy.rule", tier=CONFIDENCE_TIER_HEURISTIC)
    rare = _risk("rare.rule", tier=CONFIDENCE_TIER_HEURISTIC)
    weights = {"noisy.rule": 0.8, "rare.rule": 1.0}

    ranked = rank_findings((noisy, rare), noise_weights=weights)

    # Same severity, tier and raw confidence -> the rare rule wins on noise weight.
    assert ranked[0] is rare
    assert ranked[1] is noisy


def test_rank_findings_severity_still_dominates_noise() -> None:
    noisy_error = _risk("noisy.rule", tier=CONFIDENCE_TIER_HEURISTIC, severity="error")
    rare_warning = _risk(
        "rare.rule", tier=CONFIDENCE_TIER_HEURISTIC, severity="warning"
    )
    weights = {"noisy.rule": 0.5, "rare.rule": 1.0}

    ranked = rank_findings((rare_warning, noisy_error), noise_weights=weights)

    # Even heavily down-weighted, an error outranks a warning: noise never buries
    # a higher-severity finding.
    assert ranked[0] is noisy_error


def test_rank_findings_default_unchanged_and_tier_preserved() -> None:
    heuristic = _risk("rule", tier=CONFIDENCE_TIER_HEURISTIC)
    verified = _risk("rule", tier=CONFIDENCE_TIER_VERIFIED)

    # No weights: verified above heuristic at equal severity (historical behavior).
    ranked = rank_findings((heuristic, verified))

    assert ranked[0] is verified
    assert ranked[1] is heuristic


def test_rank_findings_preserves_all_findings() -> None:
    findings = (
        _risk("noisy.rule", tier=CONFIDENCE_TIER_HEURISTIC),
        _risk("rare.rule", tier=CONFIDENCE_TIER_VERIFIED),
    )
    weights = {"noisy.rule": 0.3, "rare.rule": 1.0}

    ranked = rank_findings(findings, noise_weights=weights)

    # Transparent: re-ranking changes order, never the set of findings.
    assert {f.finding_id for f in ranked} == {f.finding_id for f in findings}
    assert len(ranked) == len(findings)
