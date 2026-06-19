from codescent.core.models import AdaptiveSettings, FindingStatus
from codescent.services.calibration import (
    _rule_calibration,  # pyright: ignore[reportPrivateUsage]
    _suppression_candidates,  # pyright: ignore[reportPrivateUsage]
)
from codescent.storage.repositories import FindingRow

SETTINGS = AdaptiveSettings()


def _finding(
    rule_id: str,
    status: FindingStatus,
    *,
    confidence: float = 0.9,
    file_path: str = "src/pkg/a.py",
) -> FindingRow:
    return FindingRow(
        id=f"{rule_id}:{status.value}:{file_path}",
        stable_key=f"{rule_id}:{file_path}:{status.value}",
        rule_id=rule_id,
        file_path=file_path,
        severity="warning",
        confidence=confidence,
        status=status,
        title="t",
        message="m",
        evidence_json="{}",
        suggested_action="a",
        events=(),
    )


def test_cold_start_below_min_sample_uses_base_confidence() -> None:
    members = [_finding("python.large_file", FindingStatus.RESOLVED) for _ in range(5)]

    calibration = _rule_calibration("python.large_file", members, SETTINGS)

    assert calibration.calibrated is False
    assert calibration.adjusted_confidence == calibration.base_confidence
    assert calibration.sample_size == 5


def test_high_accept_rate_boosts_confidence_capped_at_one() -> None:
    members = [
        _finding("python.large_file", FindingStatus.RESOLVED, confidence=0.9)
        for _ in range(10)
    ]

    calibration = _rule_calibration("python.large_file", members, SETTINGS)

    assert calibration.calibrated is True
    assert calibration.accept_rate == 1.0
    # base 0.9 + max_delta 0.2 -> clamped to 1.0
    assert calibration.adjusted_confidence == 1.0


def test_low_accept_rate_reduces_confidence() -> None:
    members = [
        _finding("python.large_file", FindingStatus.WONTFIX, confidence=0.9)
        for _ in range(10)
    ]

    calibration = _rule_calibration("python.large_file", members, SETTINGS)

    assert calibration.calibrated is True
    assert calibration.accept_rate == 0.0
    # base 0.9 - max_delta 0.2 -> 0.7
    assert calibration.adjusted_confidence == 0.7


def test_recalibration_respects_the_confidence_floor() -> None:
    members = [
        _finding("python.duplicate_literal", FindingStatus.IGNORED, confidence=0.4)
        for _ in range(10)
    ]

    calibration = _rule_calibration("python.duplicate_literal", members, SETTINGS)

    # 0.4 - 0.2 = 0.2, clamped up to the 0.3 floor.
    assert calibration.adjusted_confidence == SETTINGS.confidence_floor


def test_deferred_and_open_findings_do_not_count_as_verdicts() -> None:
    members = [
        *[_finding("python.large_file", FindingStatus.OPEN) for _ in range(20)],
        *[_finding("python.large_file", FindingStatus.DEFERRED) for _ in range(20)],
    ]

    calibration = _rule_calibration("python.large_file", members, SETTINGS)

    assert calibration.sample_size == 0
    assert calibration.calibrated is False
    assert calibration.accept_rate is None


def test_suppression_candidates_flag_heavily_dismissed_scopes() -> None:
    members = [
        _finding(
            "python.duplicate_literal",
            FindingStatus.WONTFIX,
            file_path="src/pkg/a.py",
        )
        for _ in range(5)
    ]
    members.append(
        _finding(
            "python.duplicate_literal",
            FindingStatus.IGNORED,
            file_path="src/other/b.py",
        ),
    )

    candidates = _suppression_candidates(tuple(members), SETTINGS)

    assert len(candidates) == 1
    assert candidates[0].rule_id == "python.duplicate_literal"
    assert candidates[0].scope == "src/pkg"
    assert candidates[0].dismissals == 5
