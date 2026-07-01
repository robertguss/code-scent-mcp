from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, cast
from uuid import uuid4

from codescent.core.models import FindingStatus
from codescent.engine.packs import build_pack_registry
from codescent.engine.rules.model import (
    CodeHealthFinding,
    FindingSpec,
    build_finding,
)
from codescent.engine.source_read import read_source_lines
from codescent.engine.suppression import (
    is_scan_time_suppressed,
    match_suppressions,
    parse_ignore_directives,
)
from codescent.services.config import ConfigService
from codescent.services.coverage import coverage_findings
from codescent.services.repo_index import RepoIndexService
from codescent.services.scan_cache import (
    CACHE_VERSION,
    ScanCache,
    changed_paths,
    compute_fingerprint,
    pack_input_hashes,
)
from codescent.services.search_queries import (
    is_test_path,
    rank_test_file,
    split_test_terms,
)
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.schema import SCHEMA_VERSION

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Mapping
    from pathlib import Path

    from codescent.engine.packs import PackRegistry
    from codescent.engine.suppression import IgnoreDirective, SuppressionMatch
    from codescent.services.repo_index import IndexResult
    from codescent.storage import StorageState

logger = logging.getLogger(__name__)

# Rule-logic version tag folded into the scan-cache fingerprint so a rule change
# that ships under a new tag invalidates stale cached findings. Mirrors the
# ``rule_version`` persisted on scan_runs.
RULE_VERSION: Final = "python-mvp-1"

# Evidence keys that encode absolute source positions. They shift when unrelated
# lines move above a finding, so the re-verification fingerprint ignores them --
# a line shift must NOT invalidate a recorded verification. This is the position
# subset of engine/rules/model.py._VOLATILE_EVIDENCE_KEYS; unlike the stable_key
# fingerprint, the re-verification fingerprint KEEPS size/count magnitudes
# (line_count, count, depth, ...) so that editing the flagged symbol's body
# changes the fingerprint and re-triggers verification.
_VERIFICATION_VOLATILE_KEYS: Final = frozenset(
    {"start_line", "end_line", "line", "locations"},
)


@dataclass(frozen=True, slots=True)
class CodeHealthScanResult:
    scan_id: str
    files_scanned: int
    findings_created: int
    findings_resolved: int
    finding_ids: tuple[str, ...]
    rule_ids: tuple[str, ...]
    findings: tuple[CodeHealthFinding, ...]
    suppressed_stable_keys: frozenset[str] = frozenset()

    @property
    def active_findings(self) -> tuple[CodeHealthFinding, ...]:
        """Findings that are not inline-suppressed (drive counts + ratchet)."""
        if not self.suppressed_stable_keys:
            return self.findings
        return tuple(
            finding
            for finding in self.findings
            if finding.stable_key not in self.suppressed_stable_keys
        )


@dataclass(frozen=True, slots=True)
class CodeHealthService:
    repo_root: Path | str

    def scan(
        self,
        *,
        workers: int | None = None,
        use_cache: bool = True,
        apply_default_suppression: bool = True,
    ) -> CodeHealthScanResult:
        index_result = RepoIndexService(self.repo_root).index_repo()
        state = initialize_storage(self.repo_root)
        config = ConfigService(state.repo_root).load()
        registry = build_pack_registry(config)
        pack_scan = scan_rule_packs_cached(
            state,
            registry,
            index_result,
            workers=workers,
            use_cache=use_cache,
        )
        # Coverage + changed-source are recomputed every scan (cheap; coverage
        # reads an out-of-tree file and changed-source is empty on a no-op scan),
        # so only the rule packs ride the content-hash cache. Order is identical
        # to the serial path: packs first, then changed-source, then coverage.
        findings = (
            *pack_scan.findings,
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
            # Capture the prior evidence fingerprints BEFORE the upsert overwrites
            # evidence_json, so re-verification can detect a body change.
            previous_fingerprints = _previous_evidence_fingerprints(connection)
            suppressed_matches = (
                _compute_suppressions(connection, state.repo_root, findings)
                if config.inline_suppression
                else {}
            )
            scan_time_suppressed_keys: frozenset[str] = (
                _scan_time_suppressed_keys(findings)
                if apply_default_suppression
                else frozenset()
            )
            suppressed_keys: frozenset[str] = (
                frozenset(suppressed_matches) | scan_time_suppressed_keys
            )
            resolved_ids = _resolved_absent_ids(previous, current_stable_keys)
            regressed_ids = _regressed_ids(
                previous,
                current_stable_keys,
                suppressed_keys,
            )
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
                    RULE_VERSION,
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
                status = (
                    FindingStatus.SUPPRESSED.value
                    if finding.stable_key in suppressed_keys
                    else FindingStatus.OPEN.value
                )
                _ = connection.execute(
                    """
                    insert into findings (
                        id,
                        stable_key,
                        rule_id,
                        file_id,
                        symbol_id,
                        file_path,
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
                    ) values (?, ?, ?, ?, null, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    on conflict(stable_key) do update set
                        file_id = excluded.file_id,
                        file_path = excluded.file_path,
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
                            when excluded.status = 'suppressed' then 'suppressed'
                            when findings.status = 'suppressed' then 'open'
                            when findings.status = 'resolved' then 'regressed'
                            else findings.status
                        end
                    """,
                    (
                        finding.id,
                        finding.stable_key,
                        finding.rule_id,
                        file_ids.get(finding.file_path),
                        finding.file_path,
                        finding.severity,
                        finding.confidence,
                        status,
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
            _record_suppressions(connection, suppressed_matches, previous, now)
            _invalidate_stale_verifications(
                connection,
                findings,
                previous_fingerprints,
                now,
            )

        return CodeHealthScanResult(
            scan_id=scan_id,
            files_scanned=index_result.indexed_files,
            findings_created=len(findings),
            findings_resolved=len(resolved_ids),
            finding_ids=tuple(finding.id for finding in findings),
            rule_ids=tuple(sorted({finding.rule_id for finding in findings})),
            findings=findings,
            suppressed_stable_keys=suppressed_keys,
        )


@dataclass(frozen=True, slots=True)
class RulePackScan:
    """Result of running (or restoring from cache) the rule packs."""

    findings: tuple[CodeHealthFinding, ...]
    cache_hit: bool
    reprocessed_files: tuple[str, ...]
    total_files: int
    elapsed_seconds: float


def run_rule_packs(
    registry: PackRegistry,
    root: Path,
    *,
    workers: int,
) -> tuple[CodeHealthFinding, ...]:
    """Run every rule pack and concatenate results in fixed pack order.

    With ``workers > 1`` the packs run in a bounded thread pool, but results are
    gathered in submission (pack) order, so the merged tuple is byte-identical to
    the serial loop -- parallel == serial by construction.
    """
    packs = registry.rule_packs
    if workers <= 1 or len(packs) <= 1:
        results = [tuple(pack.scan(root, registry.config)) for pack in packs]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(pack.scan, root, registry.config) for pack in packs
            ]
            results = [tuple(future.result()) for future in futures]
    return tuple(finding for result in results for finding in result)


def scan_rule_packs_cached(
    state: StorageState,
    registry: PackRegistry,
    index_result: IndexResult,
    *,
    workers: int | None,
    use_cache: bool,
) -> RulePackScan:
    """Return rule-pack findings, reusing the content-hash cache when valid.

    A cache hit (same per-file hashes, git status, config, and engine version as
    the stored scan) reuses the cached findings verbatim and runs no rules. A
    miss re-runs the packs in parallel and refreshes the cache.
    """
    start = time.perf_counter()
    config = registry.config
    file_hashes = index_result.file_hashes
    # The language inventory only hashes .py/.ts/.js; fold in the Go and generic
    # packs' own file content so editing one of those never serves a stale scan.
    fingerprint_files = dict(file_hashes)
    fingerprint_files.update(pack_input_hashes(state.repo_root, config))
    fingerprint = compute_fingerprint(
        fingerprint_files,
        git_status=index_result.git_status,
        config_repr=repr(config),
        engine_version=f"{CACHE_VERSION}.{SCHEMA_VERSION}.{RULE_VERSION}",
    )
    cache = ScanCache(state.state_dir)
    cached = cache.load() if use_cache else None
    if cached is not None and cached.fingerprint == fingerprint:
        elapsed = time.perf_counter() - start
        logger.info(
            "scan cache hit: reused %d findings, 0/%d files reprocessed (%.3fs)",
            len(cached.findings),
            len(file_hashes),
            elapsed,
        )
        return RulePackScan(
            findings=cached.findings,
            cache_hit=True,
            reprocessed_files=(),
            total_files=len(file_hashes),
            elapsed_seconds=elapsed,
        )

    reprocessed = (
        changed_paths(cached.file_hashes, file_hashes)
        if cached is not None
        else tuple(sorted(file_hashes))
    )
    pack_count = len(registry.rule_packs)
    resolved_workers = (
        max(1, workers)
        if workers is not None
        else max(1, min((os.cpu_count() or 1) - 1, pack_count))
    )
    findings = run_rule_packs(registry, state.repo_root, workers=resolved_workers)
    if use_cache:
        cache.store(
            fingerprint=fingerprint,
            file_hashes=file_hashes,
            findings=findings,
        )
    elapsed = time.perf_counter() - start
    logger.info(
        "scan cache miss: %d findings, %d/%d reprocessed, workers=%d (%.3fs)",
        len(findings),
        len(reprocessed),
        len(file_hashes),
        resolved_workers,
        elapsed,
    )
    return RulePackScan(
        findings=findings,
        cache_hit=False,
        reprocessed_files=reprocessed,
        total_files=len(file_hashes),
        elapsed_seconds=elapsed,
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


def _verification_fingerprint(evidence: Mapping[str, object]) -> str:
    """Canonical hash material for a finding's body, minus absolute positions.

    Keeps size/count substance (line_count, count, depth, ...) so a body edit
    changes the fingerprint, but drops line positions so a benign line shift
    above the finding does not.
    """
    body = {
        key: value
        for key, value in evidence.items()
        if key not in _VERIFICATION_VOLATILE_KEYS
    }
    return json.dumps(body, sort_keys=True)


def _previous_evidence_fingerprints(
    connection: sqlite3.Connection,
) -> dict[str, str]:
    rows: list[tuple[str, str]] = connection.execute(
        "select stable_key, evidence_json from findings",
    ).fetchall()
    fingerprints: dict[str, str] = {}
    for stable_key, evidence_json in rows:
        parsed = cast("dict[str, object]", json.loads(evidence_json))
        fingerprints[stable_key] = _verification_fingerprint(parsed)
    return fingerprints


def _invalidate_stale_verifications(
    connection: sqlite3.Connection,
    findings: tuple[CodeHealthFinding, ...],
    previous_fingerprints: dict[str, str],
    now: str,
) -> None:
    """Drop recorded verifications whose finding's body changed since last scan.

    When a ``stable_key`` persists (same logical finding) but its evidence
    fingerprint changes, the symbol body was edited, so any prior passing
    verification no longer vouches for the current code. The verification ledger
    rows are removed and the staleness is logged to ``finding_events``. A line
    shift leaves the fingerprint unchanged, so the ledger stays attached.
    """
    for finding in findings:
        previous = previous_fingerprints.get(finding.stable_key)
        if previous is None or previous == _verification_fingerprint(finding.evidence):
            continue
        cursor = connection.execute(
            "delete from verification_runs where finding_id = ?",
            (finding.id,),
        )
        if cursor.rowcount > 0:
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
                    finding.id,
                    "verification_stale",
                    now,
                    json.dumps(
                        {"reason": "evidence_fingerprint_changed"},
                        sort_keys=True,
                    ),
                ),
            )


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
    suppressed_keys: frozenset[str],
) -> tuple[str, ...]:
    return tuple(
        finding_id
        for stable_key, (finding_id, status) in previous.items()
        if stable_key in current_stable_keys
        and stable_key not in suppressed_keys
        and status is FindingStatus.RESOLVED
    )


def _scan_time_suppressed_keys(
    findings: tuple[CodeHealthFinding, ...],
) -> frozenset[str]:
    """Stable keys of findings the default scan-time config drops (R4).

    Corpus fixtures (all rules) and the structural/test-hygiene noise rules in
    test scope; test-quality rules keep firing on tests. Overridable per scan
    via ``apply_default_suppression=False`` for the precision eval harness.
    """
    return frozenset(
        finding.stable_key
        for finding in findings
        if is_scan_time_suppressed(
            finding.rule_id,
            finding.file_path,
            is_test=is_test_path(finding.file_path),
        )
    )


def _compute_suppressions(
    connection: sqlite3.Connection,
    repo_root: Path,
    findings: tuple[CodeHealthFinding, ...],
) -> dict[str, SuppressionMatch]:
    directives_by_file: dict[str, tuple[IgnoreDirective, ...]] = {}
    for file_path in {finding.file_path for finding in findings}:
        source = read_source_lines(repo_root / file_path)
        if source.lines is None:
            continue
        directives = parse_ignore_directives(source.lines)
        if directives:
            directives_by_file[file_path] = directives
    if not directives_by_file:
        return {}
    symbol_lines = _symbol_start_lines(connection)
    return match_suppressions(findings, directives_by_file, symbol_lines)


def _symbol_start_lines(
    connection: sqlite3.Connection,
) -> dict[tuple[str, str], int]:
    rows: list[tuple[str, str, int]] = connection.execute(
        """
        select files.path, symbols.qualified_name, symbols.start_line
        from symbols
        join files on files.id = symbols.file_id
        """,
    ).fetchall()
    return {(path, qualified_name): start for path, qualified_name, start in rows}


def _record_suppressions(
    connection: sqlite3.Connection,
    matches: dict[str, SuppressionMatch],
    previous: dict[str, tuple[str, FindingStatus]],
    now: str,
) -> None:
    for stable_key, match in matches.items():
        prior = previous.get(stable_key)
        if prior is not None and prior[1] is FindingStatus.SUPPRESSED:
            # Already suppressed on a prior scan; don't re-log the transition.
            continue
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
                stable_key,
                "suppressed",
                now,
                json.dumps(
                    {
                        "status": FindingStatus.SUPPRESSED.value,
                        "rule_id": match.rule_id,
                        "comment": match.comment,
                    },
                    sort_keys=True,
                ),
            ),
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
