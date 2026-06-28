from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codescent.core.models import FindingStatus
from codescent.services.ci import CiService
from codescent.services.code_health import CodeHealthService
from codescent.services.findings import FindingsService

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.storage.repositories import FindingRow

logger = logging.getLogger(__name__)

_IGNORE = "# codescent: ignore[python.dead_code_candidate]"
_NEUTRAL = "# placeholder"

# Two genuinely-dead private functions; `_alpha_dead` always sits on line 2 so
# its stable key never shifts when we toggle line 1 between an ignore comment and
# a neutral one. `_beta_dead` (line 6) never has a comment above it.
_BODY = (
    "def _alpha_dead() -> int:\n"
    "    return 1\n"
    "\n"
    "\n"
    "def _beta_dead() -> int:\n"
    "    return 2\n"
)


def _write(repo: Path, first_line: str, *, extra: str = "") -> None:
    source = repo / "src" / "pkg" / "analysis.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    _ = source.write_text(f"{first_line}\n{_BODY}{extra}")


def _findings(repo: Path) -> tuple[FindingRow, ...]:
    return FindingsService(repo).get_smell_report().findings


def _by_status(repo: Path, status: FindingStatus) -> list[FindingRow]:
    return [finding for finding in _findings(repo) if finding.status is status]


def test_ignore_comment_suppresses_only_targeted_finding_with_audit(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(repo, _IGNORE)

    _ = CodeHealthService(repo).scan()

    suppressed = _by_status(repo, FindingStatus.SUPPRESSED)
    dead_open = [
        finding
        for finding in _by_status(repo, FindingStatus.OPEN)
        if finding.rule_id == "python.dead_code_candidate"
    ]
    logger.info(
        "suppressed=%s open_dead_code=%s",
        [f.evidence_json for f in suppressed],
        [f.evidence_json for f in dead_open],
    )
    assert len(suppressed) == 1, "the ignored finding should be suppressed"
    assert suppressed[0].rule_id == "python.dead_code_candidate"
    assert len(dead_open) == 1, "the un-annotated sibling finding should stay open"

    # Audit trail: a `suppressed` event recording the suppressing comment text.
    events = [
        event for event in suppressed[0].events if event.event_type == "suppressed"
    ]
    assert len(events) == 1
    assert "codescent: ignore" in events[0].details_json


def test_suppressed_excluded_from_open_counts_but_inspectable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo, _IGNORE)

    _ = CodeHealthService(repo).scan()
    report = FindingsService(repo).get_smell_report()
    backlog = FindingsService(repo).get_backlog()

    assert report.status_counts.get("suppressed") == 1
    # The suppressed finding is excluded from the open / backlog counts: on a
    # first scan everything else is open, so open == total minus the one silenced.
    assert report.open_count == len(report.findings) - 1
    assert backlog.open_count == len(report.findings) - 1
    # Still inspectable: it is listed, just under the suppressed status.
    assert any(f.status is FindingStatus.SUPPRESSED for f in report.findings)


def test_disabling_inline_suppression_keeps_findings_open(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    config = repo / ".codescent" / "config.toml"
    config.parent.mkdir(parents=True)
    _ = config.write_text("inline_suppression = false\n")
    _write(repo, _IGNORE)

    _ = CodeHealthService(repo).scan()

    report = FindingsService(repo).get_smell_report()
    assert _by_status(repo, FindingStatus.SUPPRESSED) == []
    assert "suppressed" not in report.status_counts
    assert report.open_count == len(report.findings)


def test_removing_comment_reopens_the_finding(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo, _IGNORE)
    _ = CodeHealthService(repo).scan()
    suppressed = _by_status(repo, FindingStatus.SUPPRESSED)
    assert len(suppressed) == 1
    key = suppressed[0].stable_key

    # Remove the ignore comment (same layout -> same stable key) and rescan.
    _write(repo, _NEUTRAL)
    _ = CodeHealthService(repo).scan()

    reopened = next(f for f in _findings(repo) if f.stable_key == key)
    logger.info("reopened %s -> %s", key, reopened.status)
    assert reopened.status is FindingStatus.OPEN


def test_ratchet_excludes_suppressed_new_finding(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    # Baseline: alpha + beta only.
    _write(repo, _NEUTRAL)
    _ = CiService(repo).update_baseline()

    # Add a NEW dead function that is inline-suppressed -> not new debt.
    suppressed_gamma = f"\n\n{_IGNORE}\ndef _gamma_dead() -> int:\n    return 3\n"
    _write(repo, _NEUTRAL, extra=suppressed_gamma)
    report = CiService(repo).run(threshold="medium", ratchet=True)
    logger.info("suppressed-gamma new_finding_count=%d", report.new_finding_count)
    assert report.new_finding_count == 0

    # Control: the same new function WITHOUT the comment is counted as new debt.
    open_gamma = "\n\ndef _gamma_dead() -> int:\n    return 3\n"
    _write(repo, _NEUTRAL, extra=open_gamma)
    control = CiService(repo).run(threshold="medium", ratchet=True)
    logger.info("open-gamma new_finding_count=%d", control.new_finding_count)
    assert control.new_finding_count == 1
