"""Runtime acceptance precision + health trend from the repo's own verdicts.

This is **acceptance precision** — per-rule accepted-vs-dismissed rates derived
from the persisted finding status history plus calibration suppression data. It
is distinct from the labeled-corpus **eval precision** computed by the eval
harness (``evals/``): eval precision measures rule correctness against known
fixtures, while acceptance precision measures how often humans/agents *kept* a
rule's findings in this repo.

Everything is a deterministic, pure function of the stored findings + calibration
suppression candidates: same ``.codescent`` state in, same report out. The output
is bounded — the per-rule list is bounded by the active rule set, and the trend
is capped to the most recent ``_MAX_TREND_POINTS`` daily points.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from codescent.core.models import FindingStatus
from codescent.services.calibration import CalibrationService
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository, FindingRow

# A finding the user kept and fixed counts as accepted; one explicitly rejected
# counts as dismissed. Mirrors calibration's accept-rate so the two stay
# consistent (open/deferred/needs-review are not yet verdicts).
_ACCEPTED_STATUSES = frozenset({FindingStatus.RESOLVED})
_DISMISSED_STATUSES = frozenset({FindingStatus.WONTFIX, FindingStatus.IGNORED})
_STATUS_CHANGED_EVENT = "status_changed"
# ponytail: cap the trend to the last 90 daily points; raise if longer history
# ever needs surfacing.
_MAX_TREND_POINTS = 90


@dataclass(frozen=True, slots=True)
class RulePrecision:
    rule_id: str
    accepted: int
    dismissed: int
    sample_size: int
    acceptance_precision: float | None
    suppression_candidates: int


@dataclass(frozen=True, slots=True)
class HealthTrendPoint:
    date: str
    accepted: int
    dismissed: int
    acceptance_precision: float | None


@dataclass(frozen=True, slots=True)
class PrecisionReport:
    rules: tuple[RulePrecision, ...]
    trend: tuple[HealthTrendPoint, ...]
    accepted: int
    dismissed: int
    sample_size: int
    acceptance_precision: float | None


@dataclass(frozen=True, slots=True)
class PrecisionService:
    repo_root: Path | str

    def get_precision(self) -> PrecisionReport:
        findings = _repository(self.repo_root).list_findings()
        return build_precision_report(findings, self._suppression_by_rule())

    def acceptance_precision_by_rule(self) -> dict[str, float | None]:
        """Per-rule acceptance precision keyed by ``rule_id``.

        Consumed by confidence-badges: read ``acceptance_precision`` for a
        finding's ``rule_id`` (``None`` when the rule has no verdicts yet).
        """
        return {
            rule.rule_id: rule.acceptance_precision
            for rule in self.get_precision().rules
        }

    def _suppression_by_rule(self) -> dict[str, int]:
        candidates = (
            CalibrationService(
                self.repo_root,
            )
            .get_calibration()
            .suppression_candidates
        )
        counts: dict[str, int] = defaultdict(int)
        for candidate in candidates:
            counts[candidate.rule_id] += 1
        return dict(counts)


def build_precision_report(
    findings: tuple[FindingRow, ...],
    suppression_by_rule: dict[str, int] | None = None,
) -> PrecisionReport:
    suppression = suppression_by_rule or {}
    rules = _rule_precisions(findings, suppression)
    accepted = sum(rule.accepted for rule in rules)
    dismissed = sum(rule.dismissed for rule in rules)
    return PrecisionReport(
        rules=rules,
        trend=_health_trend(findings),
        accepted=accepted,
        dismissed=dismissed,
        sample_size=accepted + dismissed,
        acceptance_precision=_precision(accepted, dismissed),
    )


def _rule_precisions(
    findings: tuple[FindingRow, ...],
    suppression_by_rule: dict[str, int],
) -> tuple[RulePrecision, ...]:
    accepted_by_rule: dict[str, int] = defaultdict(int)
    dismissed_by_rule: dict[str, int] = defaultdict(int)
    for finding in findings:
        if finding.status in _ACCEPTED_STATUSES:
            accepted_by_rule[finding.rule_id] += 1
        elif finding.status in _DISMISSED_STATUSES:
            dismissed_by_rule[finding.rule_id] += 1
    rule_ids = set(accepted_by_rule) | set(dismissed_by_rule) | set(suppression_by_rule)
    rules = [
        RulePrecision(
            rule_id=rule_id,
            accepted=accepted_by_rule[rule_id],
            dismissed=dismissed_by_rule[rule_id],
            sample_size=accepted_by_rule[rule_id] + dismissed_by_rule[rule_id],
            acceptance_precision=_precision(
                accepted_by_rule[rule_id],
                dismissed_by_rule[rule_id],
            ),
            suppression_candidates=suppression_by_rule.get(rule_id, 0),
        )
        for rule_id in rule_ids
    ]
    return tuple(sorted(rules, key=lambda rule: rule.rule_id))


def _health_trend(findings: tuple[FindingRow, ...]) -> tuple[HealthTrendPoint, ...]:
    # Replay verdict transitions in time order and snapshot the cumulative
    # accepted/dismissed state at the end of each day. Net-state replay means a
    # finding that flips verdict (e.g. resolved -> reopened) is corrected rather
    # than double-counted, so the final point matches the per-rule totals.
    verdict_events = sorted(
        (event.created_at, finding.id, status)
        for finding in findings
        for event in finding.events
        if event.event_type == _STATUS_CHANGED_EVENT
        for status in (_event_status(event.details_json),)
        if status is not None
    )
    state: dict[str, str] = {}
    accepted = dismissed = 0
    daily: dict[str, tuple[int, int]] = {}
    order: list[str] = []
    for created_at, finding_id, status in verdict_events:
        verdict = _verdict(status)
        previous = state.get(finding_id)
        if verdict == previous:
            continue
        accepted, dismissed = _apply_transition(
            accepted,
            dismissed,
            previous=previous,
            verdict=verdict,
        )
        if verdict is None:
            _ = state.pop(finding_id, None)
        else:
            state[finding_id] = verdict
        date = created_at[:10]
        if date not in daily:
            order.append(date)
        daily[date] = (accepted, dismissed)
    points = tuple(
        HealthTrendPoint(
            date=date,
            accepted=daily[date][0],
            dismissed=daily[date][1],
            acceptance_precision=_precision(*daily[date]),
        )
        for date in order
    )
    return points[-_MAX_TREND_POINTS:]


def _apply_transition(
    accepted: int,
    dismissed: int,
    *,
    previous: str | None,
    verdict: str | None,
) -> tuple[int, int]:
    if previous == "accepted":
        accepted -= 1
    elif previous == "dismissed":
        dismissed -= 1
    if verdict == "accepted":
        accepted += 1
    elif verdict == "dismissed":
        dismissed += 1
    return accepted, dismissed


def _verdict(status_value: str) -> str | None:
    try:
        status = FindingStatus(status_value)
    except ValueError:
        return None
    if status in _ACCEPTED_STATUSES:
        return "accepted"
    if status in _DISMISSED_STATUSES:
        return "dismissed"
    return None


def _event_status(details_json: str) -> str | None:
    try:
        raw = cast("object", json.loads(details_json))
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    details = cast("dict[str, object]", raw)
    status = details.get("status")
    return status if isinstance(status, str) else None


def _precision(accepted: int, dismissed: int) -> float | None:
    total = accepted + dismissed
    if total == 0:
        return None
    return round(accepted / total, 3)


def _repository(repo_root: Path | str) -> FindingRepository:
    state = initialize_storage(Path(repo_root))
    return FindingRepository(RepositoryStorage(state))
