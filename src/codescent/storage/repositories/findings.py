from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from codescent.core.models import FindingStatus

if TYPE_CHECKING:
    from codescent.storage import RepositoryStorage


@dataclass(frozen=True, slots=True)
class FindingEventRow:
    event_type: str
    created_at: str
    details_json: str


@dataclass(frozen=True, slots=True)
class FindingRow:
    id: str
    stable_key: str
    rule_id: str
    file_path: str
    severity: str
    confidence: float
    status: FindingStatus
    title: str
    message: str
    evidence_json: str
    suggested_action: str
    events: tuple[FindingEventRow, ...]


@dataclass(frozen=True, slots=True)
class FindingRepository:
    storage: RepositoryStorage

    def list_findings(self) -> tuple[FindingRow, ...]:
        with self.storage.read_connection() as connection:
            rows: list[
                tuple[str, str, str, str | None, str, float, str, str, str, str, str]
            ] = connection.execute(
                """
                select
                    findings.id,
                    findings.stable_key,
                    findings.rule_id,
                    files.path,
                    findings.severity,
                    findings.confidence,
                    findings.status,
                    findings.title,
                    findings.message,
                    findings.evidence_json,
                    coalesce(findings.suggested_action, '')
                from findings
                left join files on files.id = findings.file_id
                order by findings.status, findings.severity, findings.rule_id
                """,
            ).fetchall()
            events_by_finding = self._events_by_finding()
        return tuple(
            FindingRow(
                id=row[0],
                stable_key=row[1],
                rule_id=row[2],
                file_path=row[3] or "",
                severity=row[4],
                confidence=row[5],
                status=FindingStatus(row[6]),
                title=row[7],
                message=row[8],
                evidence_json=row[9],
                suggested_action=row[10],
                events=events_by_finding.get(row[0], ()),
            )
            for row in rows
        )

    def update_status(
        self,
        finding_id: str,
        status: FindingStatus,
        *,
        note: str,
    ) -> FindingRow:
        now = datetime.now(UTC).isoformat()
        with self.storage.write_transaction() as connection:
            _ = connection.execute(
                "update findings set status = ?, resolved_at = ? where id = ?",
                (
                    status.value,
                    now if status is FindingStatus.RESOLVED else None,
                    finding_id,
                ),
            )
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
                    "status_changed",
                    now,
                    json.dumps({"status": status.value, "note": note}),
                ),
            )
        return self.get_finding(finding_id)

    def get_finding(self, finding_id: str) -> FindingRow:
        for finding in self.list_findings():
            if finding.id == finding_id:
                return finding
        raise LookupError(finding_id)

    def _events_by_finding(self) -> dict[str, tuple[FindingEventRow, ...]]:
        with self.storage.read_connection() as connection:
            rows: list[tuple[str, str, str, str]] = connection.execute(
                """
                select finding_id, event_type, created_at, details_json
                from finding_events
                order by created_at
                """,
            ).fetchall()
        grouped: dict[str, list[FindingEventRow]] = {}
        for finding_id, event_type, created_at, details_json in rows:
            grouped.setdefault(finding_id, []).append(
                FindingEventRow(
                    event_type=event_type,
                    created_at=created_at,
                    details_json=details_json,
                ),
            )
        return {finding_id: tuple(events) for finding_id, events in grouped.items()}
