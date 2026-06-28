from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from codescent.core.models import FindingStatus
from codescent.engine.packs import build_pack_registry
from codescent.engine.rules.model import (
    CodeHealthFinding,
    FindingSpec,
    build_finding,
)
from codescent.engine.source_read import read_source_lines
from codescent.services.config import ConfigService
from codescent.services.coverage import coverage_findings
from codescent.services.repo_index import RepoIndexService
from codescent.services.search_queries import (
    is_test_path,
    rank_test_file,
    split_test_terms,
)
from codescent.storage import RepositoryStorage, initialize_storage

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class CodeHealthScanResult:
    scan_id: str
    files_scanned: int
    findings_created: int
    findings_resolved: int
    finding_ids: tuple[str, ...]
    rule_ids: tuple[str, ...]
    findings: tuple[CodeHealthFinding, ...]


@dataclass(frozen=True, slots=True)
class CodeHealthService:
    repo_root: Path | str

    def scan(self) -> CodeHealthScanResult:
        index_result = RepoIndexService(self.repo_root).index_repo()
        state = initialize_storage(self.repo_root)
        config = ConfigService(state.repo_root).load()
        registry = build_pack_registry(config)
        findings = (
            *registry.scan_rule_packs(state.repo_root),
            *_changed_source_without_related_tests(
                state.repo_root,
                index_result.changed_files,
                set(index_result.file_hashes),
            ),
            *coverage_findings(state.repo_root, coverage_path=config.coverage_path),
        )
        scan_id = uuid4().hex
        now = datetime.now(UTC).isoformat()
        storage = RepositoryStorage(state)
        current_stable_keys = {finding.stable_key for finding in findings}

        with storage.write_transaction() as connection:
            previous = _previous_lifecycle(connection)
            resolved_ids = _resolved_absent_ids(previous, current_stable_keys)
            regressed_ids = _regressed_ids(previous, current_stable_keys)
            _ = connection.execute(
                """
                insert into scan_runs (
                    id,
                    started_at,
                    completed_at,
                    index_version,
                    rule_version,
                    files_scanned,
                    findings_created,
                    findings_resolved,
                    status
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scan_id,
                    now,
                    now,
                    1,
                    "python-mvp-1",
                    index_result.indexed_files,
                    len(findings),
                    len(resolved_ids),
                    "complete",
                ),
            )
            file_ids = dict(
                connection.execute("select path, id from files").fetchall(),
            )
            for finding in findings:
                _ = connection.execute(
                    """
                    insert into findings (
                        id,
                        stable_key,
                        rule_id,
                        file_id,
                        symbol_id,
                        severity,
                        confidence,
                        status,
                        title,
                        message,
                        evidence_json,
                        suggested_action,
                        confidence_tier,
                        provenance_json,
                        first_seen_scan_id,
                        last_seen_scan_id
                    ) values (?, ?, ?, ?, null, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    on conflict(stable_key) do update set
                        file_id = excluded.file_id,
                        last_seen_scan_id = excluded.last_seen_scan_id,
                        evidence_json = excluded.evidence_json,
                        confidence = excluded.confidence,
                        confidence_tier = excluded.confidence_tier,
                        provenance_json = excluded.provenance_json,
                        resolved_at = case
                            when findings.status = 'resolved' then null
                            else findings.resolved_at
                        end,
                        status = case
                            when findings.status = 'resolved' then 'regressed'
                            else findings.status
                        end
                    """,
                    (
                        finding.id,
                        finding.stable_key,
                        finding.rule_id,
                        file_ids.get(finding.file_path),
                        finding.severity,
                        finding.confidence,
                        "open",
                        finding.title,
                        finding.message,
                        json.dumps(finding.evidence, sort_keys=True),
                        finding.suggested_action,
                        finding.confidence_tier,
                        json.dumps(finding.provenance, sort_keys=True),
                        scan_id,
                        scan_id,
                    ),
                )
            _record_resolved_absent(connection, resolved_ids, now)
            _record_regressed(connection, regressed_ids, now)

        return CodeHealthScanResult(
            scan_id=scan_id,
            files_scanned=index_result.indexed_files,
            findings_created=len(findings),
            findings_resolved=len(resolved_ids),
            finding_ids=tuple(finding.id for finding in findings),
            rule_ids=tuple(sorted({finding.rule_id for finding in findings})),
            findings=findings,
        )


def _changed_source_without_related_tests(
    repo_root: Path,
    changed_files: tuple[str, ...],
    indexed_paths: set[str],
) -> tuple[CodeHealthFinding, ...]:
    return tuple(
        build_finding(
            FindingSpec(
                rule_id="python.changed_source_without_related_test",
                title="Changed source file without related test",
                message=f"{path} changed without an obvious related test file.",
                file_path=path,
                symbol=None,
                severity="info",
                confidence=0.6,
                evidence={"expected_test": _expected_test_path(path)},
                suggested_action=(
                    "Add or update the related test before changing behavior."
                ),
            ),
        )
        for path in changed_files
        if _is_python_source(path)
        and not _has_likely_test(repo_root, path, indexed_paths)
    )


def _is_python_source(path: str) -> bool:
    name = path.rsplit("/", maxsplit=1)[-1]
    return path.endswith(".py") and not name.startswith("test_")


def _expected_test_path(path: str) -> str:
    stem = path.rsplit("/", maxsplit=1)[-1].removesuffix(".py")
    return f"tests/test_{stem}.py"


def _has_likely_test(
    repo_root: Path,
    source_path: str,
    indexed_paths: set[str],
) -> bool:
    terms = split_test_terms(source_path)
    for test_path in sorted(indexed_paths):
        if not is_test_path(test_path):
            continue
        try:
            source = read_source_lines(repo_root / test_path)
        except OSError:
            continue
        if source.lines is None:
            continue
        lines = list(source.lines)
        _, reasons, _ = rank_test_file(test_path, lines, terms)
        if any(
            reason in {"content_match", "path_match", "symbol_match"}
            for reason in reasons
        ):
            return True
    return False


def _previous_lifecycle(
    connection: sqlite3.Connection,
) -> dict[str, tuple[str, FindingStatus]]:
    rows: list[tuple[str, str, str]] = connection.execute(
        "select stable_key, id, status from findings",
    ).fetchall()
    return {
        stable_key: (finding_id, FindingStatus(status))
        for stable_key, finding_id, status in rows
    }


def _resolved_absent_ids(
    previous: dict[str, tuple[str, FindingStatus]],
    current_stable_keys: set[str],
) -> tuple[str, ...]:
    return tuple(
        finding_id
        for stable_key, (finding_id, status) in previous.items()
        if stable_key not in current_stable_keys
        and status
        in {
            FindingStatus.OPEN,
            FindingStatus.IN_PROGRESS,
            FindingStatus.REGRESSED,
            FindingStatus.NEEDS_REVIEW,
        }
    )


def _regressed_ids(
    previous: dict[str, tuple[str, FindingStatus]],
    current_stable_keys: set[str],
) -> tuple[str, ...]:
    return tuple(
        finding_id
        for stable_key, (finding_id, status) in previous.items()
        if stable_key in current_stable_keys and status is FindingStatus.RESOLVED
    )


def _record_resolved_absent(
    connection: sqlite3.Connection,
    finding_ids: tuple[str, ...],
    now: str,
) -> None:
    for finding_id in finding_ids:
        _ = connection.execute(
            "update findings set status = ?, resolved_at = ? where id = ?",
            (FindingStatus.RESOLVED.value, now, finding_id),
        )
        _record_event(connection, finding_id, "resolved", FindingStatus.RESOLVED, now)


def _record_regressed(
    connection: sqlite3.Connection,
    finding_ids: tuple[str, ...],
    now: str,
) -> None:
    for finding_id in finding_ids:
        _record_event(connection, finding_id, "regressed", FindingStatus.REGRESSED, now)


def _record_event(
    connection: sqlite3.Connection,
    finding_id: str,
    event_type: str,
    status: FindingStatus,
    now: str,
) -> None:
    _ = connection.execute(
        """
        insert into finding_events (
            finding_id,
            event_type,
            created_at,
            details_json
        ) values (?, ?, ?, ?)
        """,
        (
            finding_id,
            event_type,
            now,
            json.dumps({"status": status.value}),
        ),
    )
