"""Per-repo severity calibration — e2e over two synthetic repos.

A *noisy* repo (one rule dominates) and a *clean* repo (rules are balanced) are
seeded into real `.codescent` storage. The per-repo noise baseline is derived
from storage and fed into `rank_findings`; the noisy repo's rare rule rises above
the dominant one while the clean repo's ordering is left neutral. The derived
baseline and adjusted ranks are logged for inspection.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codescent.services.calibration import CalibrationService
from codescent.services.risk import RiskFinding, rank_findings
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

logger = logging.getLogger(__name__)


def _seed(repo: Path, rule_ids: list[str]) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    storage = RepositoryStorage(initialize_storage(repo))
    with storage.write_transaction() as connection:
        _ = connection.execute(
            """
            insert or ignore into scan_runs (
                id, started_at, completed_at, index_version, rule_version,
                files_scanned, findings_created, findings_resolved, status
            ) values ('scan', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z',
                1, 'test', 0, 0, 0, 'complete')
            """,
        )
        for index, rule_id in enumerate(rule_ids):
            path = f"src/pkg/f{index}.py"
            cursor = connection.execute(
                """
                insert into files (
                    path, language, hash, size_bytes, line_count,
                    is_generated, is_test
                ) values (?, 'python', ?, 1, 10, 0, 0)
                """,
                (path, f"hash-{index}"),
            )
            _ = connection.execute(
                """
                insert into findings (
                    id, stable_key, rule_id, file_id, severity, confidence,
                    status, title, message, evidence_json, suggested_action,
                    first_seen_scan_id, last_seen_scan_id
                ) values (?, ?, ?, ?, 'warning', 0.8, 'open', ?, ?, '{}', '',
                    'scan', 'scan')
                """,
                (
                    f"{rule_id}:{index}",
                    f"{rule_id}:{path}",
                    rule_id,
                    cursor.lastrowid,
                    "t",
                    "m",
                ),
            )


def _ranked(repo: Path) -> tuple[tuple[str, ...], dict[str, float]]:
    weights = CalibrationService(repo).get_noise_baseline().weight_map()
    findings = tuple(
        RiskFinding(
            finding_id=row.id,
            rule_id=row.rule_id,
            file_path=row.file_path,
            severity=row.severity,
            confidence=row.confidence,
            confidence_tier=row.confidence_tier,
            status=row.status.value,
        )
        for row in FindingRepository(
            RepositoryStorage(initialize_storage(repo)),
        ).list_findings()
    )
    ranked = rank_findings(findings, noise_weights=weights)
    return tuple(f.rule_id for f in ranked), weights


def test_noisy_vs_clean_repo_ranking_adapts(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    noisy_repo = tmp_path / "noisy"
    clean_repo = tmp_path / "clean"
    # Noisy: "python.todo_cluster" fires everywhere, "python.dead_code" is rare.
    _seed(noisy_repo, ["python.todo_cluster"] * 9 + ["python.dead_code"])
    # Clean: two rules are balanced (no single rule dominates).
    _seed(clean_repo, ["python.todo_cluster", "python.dead_code"] * 5)

    with caplog.at_level(logging.INFO):
        noisy_ranks, noisy_weights = _ranked(noisy_repo)
        clean_ranks, clean_weights = _ranked(clean_repo)
        # Log baseline + adjusted ranks (inspectable).
        logger.info(
            "noisy baseline weights=%s adjusted_ranks=%s", noisy_weights, noisy_ranks
        )
        logger.info(
            "clean baseline weights=%s adjusted_ranks=%s", clean_weights, clean_ranks
        )

    assert "noisy baseline weights" in caplog.text
    assert "adjusted_ranks" in caplog.text

    # Noisy repo: the rare rule is down-weighted less, so its finding ranks first.
    assert noisy_weights["python.dead_code"] > noisy_weights["python.todo_cluster"]
    assert noisy_ranks[0] == "python.dead_code"

    # Clean repo: balanced firing rates -> equal weights -> no rule is buried.
    assert clean_weights["python.todo_cluster"] == clean_weights["python.dead_code"]

    # Transparent: nothing hidden — every seeded finding is still ranked.
    assert len(noisy_ranks) == 10
    assert len(clean_ranks) == 10
