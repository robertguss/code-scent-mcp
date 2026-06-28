"""Adaptive, self-calibrating findings from the repo's own lifecycle verdicts.

CodeScent already records what humans/agents did with each finding (resolved,
wontfix, ignored). This service turns that history into:

- empirical per-rule confidence recalibration — pull a rule's confidence toward
  its observed accept rate once enough verdicts exist; and
- learned-suppression candidates — rule + directory scopes dismissed often
  enough to be auto-deferred.

Everything is a deterministic, pure function of the stored findings: same
``.codescent`` state in, same calibration out. Below the configured sample size
the base confidence is used unchanged (cold start), so new repos see no change.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from codescent.core.models import FindingStatus
from codescent.services.config import ConfigService
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository

if TYPE_CHECKING:
    from codescent.core.models import AdaptiveSettings
    from codescent.storage.repositories import FindingRow

_ACCEPTED_STATUSES = frozenset({FindingStatus.RESOLVED})
_REJECTED_STATUSES = frozenset({FindingStatus.WONTFIX, FindingStatus.IGNORED})


@dataclass(frozen=True, slots=True)
class RuleCalibration:
    rule_id: str
    base_confidence: float
    adjusted_confidence: float
    accepted: int
    rejected: int
    sample_size: int
    accept_rate: float | None
    calibrated: bool


@dataclass(frozen=True, slots=True)
class SuppressionCandidate:
    rule_id: str
    scope: str
    dismissals: int


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    rules: tuple[RuleCalibration, ...]
    suppression_candidates: tuple[SuppressionCandidate, ...]
    confidence_recalibration: bool
    learned_suppression: bool
    min_sample_size: int


@dataclass(frozen=True, slots=True)
class RuleNoiseBaseline:
    rule_id: str
    firing_count: int
    total_findings: int
    firing_rate: float
    noise_weight: float
    normalized: bool


@dataclass(frozen=True, slots=True)
class NoiseBaselineReport:
    rules: tuple[RuleNoiseBaseline, ...]
    total_findings: int
    normalized: bool
    min_sample_size: int

    def weight_map(self) -> dict[str, float]:
        return {rule.rule_id: rule.noise_weight for rule in self.rules}


@dataclass(frozen=True, slots=True)
class CalibrationService:
    repo_root: Path | str

    def get_calibration(self) -> CalibrationReport:
        settings = ConfigService(self.repo_root).load().adaptive
        findings = _repository(self.repo_root).list_findings()
        rules = _rule_calibrations(findings, settings)
        suppression = (
            _suppression_candidates(findings, settings)
            if settings.learned_suppression
            else ()
        )
        return CalibrationReport(
            rules=rules,
            suppression_candidates=suppression,
            confidence_recalibration=settings.confidence_recalibration,
            learned_suppression=settings.learned_suppression,
            min_sample_size=settings.min_sample_size,
        )

    def adjusted_confidence(self, rule_id: str) -> RuleCalibration | None:
        # Calibrate only the requested rule rather than building the whole-repo
        # report, so a single explain_score lookup does not group every rule.
        settings = ConfigService(self.repo_root).load().adaptive
        members = [
            finding
            for finding in _repository(self.repo_root).list_findings()
            if finding.rule_id == rule_id
        ]
        if not members:
            return None
        return _rule_calibration(rule_id, members, settings)

    def get_noise_baseline(self) -> NoiseBaselineReport:
        # Per-repo baseline noise: how often each rule fires across the repo. A
        # rule that fires everywhere is down-weighted in ranking; a rare rule
        # stands out. Pure, deterministic function of the stored findings (same
        # findings in -> same baseline out); extends the adaptive system rather
        # than adding a parallel one. No finding is hidden -- only re-ranked.
        settings = ConfigService(self.repo_root).load().adaptive
        findings = _repository(self.repo_root).list_findings()
        return _noise_baseline(findings, settings)


def _rule_calibrations(
    findings: tuple[FindingRow, ...],
    settings: AdaptiveSettings,
) -> tuple[RuleCalibration, ...]:
    grouped: dict[str, list[FindingRow]] = defaultdict(list)
    for finding in findings:
        grouped[finding.rule_id].append(finding)
    calibrations = [
        _rule_calibration(rule_id, members, settings)
        for rule_id, members in grouped.items()
    ]
    return tuple(sorted(calibrations, key=lambda item: item.rule_id))


def _rule_calibration(
    rule_id: str,
    members: list[FindingRow],
    settings: AdaptiveSettings,
) -> RuleCalibration:
    base_confidence = members[0].confidence
    accepted = sum(1 for member in members if member.status in _ACCEPTED_STATUSES)
    rejected = sum(1 for member in members if member.status in _REJECTED_STATUSES)
    sample_size = accepted + rejected
    calibrated = (
        settings.confidence_recalibration and sample_size >= settings.min_sample_size
    )
    accept_rate = accepted / sample_size if sample_size else None
    adjusted = (
        _adjust(base_confidence, accept_rate, settings)
        if calibrated and accept_rate is not None
        else base_confidence
    )
    return RuleCalibration(
        rule_id=rule_id,
        base_confidence=round(base_confidence, 3),
        adjusted_confidence=round(adjusted, 3),
        accepted=accepted,
        rejected=rejected,
        sample_size=sample_size,
        accept_rate=round(accept_rate, 3) if accept_rate is not None else None,
        calibrated=calibrated,
    )


def _adjust(
    base_confidence: float,
    accept_rate: float,
    settings: AdaptiveSettings,
) -> float:
    # Pull confidence toward the empirical accept rate, bounded by the delta and
    # never below the floor: accept_rate 1.0 boosts, 0.0 reduces, 0.5 is neutral.
    shift = settings.max_confidence_delta * (2.0 * accept_rate - 1.0)
    return _clamp(base_confidence + shift, settings.confidence_floor, 1.0)


def _noise_baseline(
    findings: tuple[FindingRow, ...],
    settings: AdaptiveSettings,
) -> NoiseBaselineReport:
    counts: dict[str, int] = defaultdict(int)
    for finding in findings:
        counts[finding.rule_id] += 1
    total = len(findings)
    # Cold start: a small repo lacks a stable baseline, so leave ranking
    # untouched (weight 1.0) until enough findings exist -- the same guard the
    # confidence recalibration uses, gated by the same master switch.
    normalized = settings.confidence_recalibration and total >= settings.min_sample_size
    baselines = [
        _rule_noise(rule_id, count, total, settings, normalized=normalized)
        for rule_id, count in counts.items()
    ]
    return NoiseBaselineReport(
        rules=tuple(sorted(baselines, key=lambda item: item.rule_id)),
        total_findings=total,
        normalized=normalized,
        min_sample_size=settings.min_sample_size,
    )


def _rule_noise(
    rule_id: str,
    count: int,
    total: int,
    settings: AdaptiveSettings,
    *,
    normalized: bool,
) -> RuleNoiseBaseline:
    firing_rate = count / total if total else 0.0
    # Higher firing rate -> lower weight (noisier), bounded by the same delta and
    # floor as confidence recalibration so the adjustment stays transparent and
    # never zeroes a finding out (it is re-ranked, never hidden).
    weight = (
        _clamp(
            1.0 - settings.max_confidence_delta * firing_rate,
            settings.confidence_floor,
            1.0,
        )
        if normalized
        else 1.0
    )
    return RuleNoiseBaseline(
        rule_id=rule_id,
        firing_count=count,
        total_findings=total,
        firing_rate=round(firing_rate, 3),
        noise_weight=round(weight, 3),
        normalized=normalized,
    )


def _suppression_candidates(
    findings: tuple[FindingRow, ...],
    settings: AdaptiveSettings,
) -> tuple[SuppressionCandidate, ...]:
    dismissals: dict[tuple[str, str], int] = defaultdict(int)
    for finding in findings:
        if finding.status in _REJECTED_STATUSES:
            dismissals[(finding.rule_id, _directory(finding.file_path))] += 1
    candidates = [
        SuppressionCandidate(rule_id=rule_id, scope=scope, dismissals=count)
        for (rule_id, scope), count in dismissals.items()
        if count >= settings.suppression_threshold
    ]
    return tuple(
        sorted(
            candidates, key=lambda item: (-item.dismissals, item.rule_id, item.scope)
        ),
    )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _directory(file_path: str) -> str:
    return str(PurePosixPath(file_path).parent)


def _repository(repo_root: Path | str) -> FindingRepository:
    state = initialize_storage(Path(repo_root))
    return FindingRepository(RepositoryStorage(state))
