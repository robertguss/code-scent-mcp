from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Final

from codescent.core.models import FindingStatus
from codescent.core.paths import normalize_repo_path, resolve_repo_root
from codescent.services.context import ContextService
from codescent.services.findings import FindingsService
from codescent.services.freshness import (
    AdvisoryConfidence,
    FreshnessMetadata,
    confidence_for_results,
    ensure_fresh_index,
    next_tools_with_refresh_recovery,
    warnings_for_results,
)
from codescent.services.search import SearchService

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from codescent.storage.repositories import FindingRow

RELEVANT_FILE_LIMIT: Final = 8
RELEVANT_SYMBOL_LIMIT: Final = 12
RELATED_TEST_LIMIT: Final = 8
OPEN_FINDING_LIMIT: Final = 10
SEED_FILE_LIMIT: Final = 4
RELATED_FILE_LIMIT: Final = 6
ACTIONABLE_STATUSES: Final = frozenset(
    {
        FindingStatus.OPEN,
        FindingStatus.IN_PROGRESS,
        FindingStatus.NEEDS_REVIEW,
        FindingStatus.REGRESSED,
    },
)


@dataclass(frozen=True, slots=True)
class TaskBrief:
    query: str
    relevant_files: tuple[str, ...]
    relevant_symbols: tuple[str, ...]
    related_tests: tuple[str, ...]
    open_findings: tuple[dict[str, str], ...]
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None
    warnings: tuple[str, ...]
    confidence: AdvisoryConfidence
    next_tools: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StartTaskRequest:
    query: str
    focus_path: str | None = None
    focus_symbol: str | None = None


@dataclass(frozen=True, slots=True)
class TaskBriefService:
    repo_root: Path | str

    def start_task(
        self,
        query: str,
        *,
        focus_path: str | None = None,
        focus_symbol: str | None = None,
    ) -> TaskBrief:
        repo_root = resolve_repo_root(self.repo_root)
        freshness = ensure_fresh_index(repo_root)
        context = ContextService(repo_root)
        search = SearchService(repo_root)
        request = StartTaskRequest(
            query=query,
            focus_path=focus_path,
            focus_symbol=focus_symbol,
        )
        symbol_candidates: list[str] = []
        seed_files = _seed_files(
            repo_root=repo_root,
            context=context,
            search=search,
            request=request,
            symbol_candidates=symbol_candidates,
        )

        file_candidates: list[str] = list(seed_files)
        test_candidates: list[str] = []

        for path in seed_files:
            if _is_test_path(path):
                test_candidates.append(path)
            try:
                file_context = context.get_file_context(path)
                related = context.get_related_files(path, limit=RELATED_FILE_LIMIT)
            except LookupError:
                continue

            file_candidates.append(file_context["path"])
            symbol_candidates.extend(_qualified_symbols(file_context["next_tools"]))
            test_candidates.extend(file_context["likely_tests"])

            for result in related["results"]:
                related_path = result["path"]
                if _is_test_path(related_path):
                    test_candidates.append(related_path)
                else:
                    file_candidates.append(related_path)

        relevant_files = _dedupe_cap(file_candidates, RELEVANT_FILE_LIMIT)
        relevant_symbols = _dedupe_cap(symbol_candidates, RELEVANT_SYMBOL_LIMIT)
        related_tests = _dedupe_cap(test_candidates, RELATED_TEST_LIMIT)
        open_findings = _open_findings(repo_root, set(relevant_files))
        has_results = bool(
            relevant_files or relevant_symbols or related_tests or open_findings
        )

        return TaskBrief(
            query=query,
            relevant_files=relevant_files,
            relevant_symbols=relevant_symbols,
            related_tests=related_tests,
            open_findings=open_findings,
            index_fresh=freshness.index_fresh,
            index_was_stale=freshness.index_was_stale,
            auto_refreshed=freshness.auto_refreshed,
            changed_files=freshness.changed_files,
            refresh_error=freshness.refresh_error,
            warnings=warnings_for_results(
                has_results=has_results,
                result_kind="task brief context",
                freshness=freshness,
            ),
            confidence=confidence_for_results(
                has_results=has_results,
                freshness=freshness,
            ),
            next_tools=_next_tools(
                relevant_symbols,
                open_findings,
                freshness=freshness,
                has_results=has_results,
            ),
        )


def _seed_files(
    *,
    repo_root: Path,
    context: ContextService,
    search: SearchService,
    request: StartTaskRequest,
    symbol_candidates: list[str],
) -> tuple[str, ...]:
    if request.focus_path is not None:
        return (_repo_relative_path(repo_root, request.focus_path),)

    if request.focus_symbol is not None:
        matches = context.find_symbol(request.focus_symbol, limit=3)
        symbol_candidates.extend(match["qualified_name"] for match in matches)
        symbol_paths = _dedupe_cap(
            (match["path"] for match in matches),
            SEED_FILE_LIMIT,
        )
        if symbol_paths:
            return symbol_paths

    return _query_seed_files(search, request.query)


def _query_seed_files(search: SearchService, query: str) -> tuple[str, ...]:
    if not query.strip():
        return ()
    file_results = search.search_files(query, limit=SEED_FILE_LIMIT)
    content_results = search.search_content(query, limit=SEED_FILE_LIMIT)
    return _dedupe_cap(
        (
            *(result["path"] for result in file_results),
            *(result["path"] for result in content_results),
        ),
        SEED_FILE_LIMIT,
    )


def _repo_relative_path(repo_root: Path, path: str) -> str:
    return normalize_repo_path(repo_root, path).relative_to(repo_root).as_posix()


def _qualified_symbols(next_tools: tuple[str, ...]) -> tuple[str, ...]:
    prefix = "get_symbol_context:"
    return tuple(
        tool.removeprefix(prefix) for tool in next_tools if tool.startswith(prefix)
    )


def _open_findings(
    repo_root: Path,
    relevant_files: set[str],
) -> tuple[dict[str, str], ...]:
    if not relevant_files:
        return ()

    findings = sorted(
        FindingsService(repo_root).get_smell_report().findings,
        key=lambda finding: (finding.file_path, finding.rule_id, finding.id),
    )
    return tuple(
        _finding_payload(finding)
        for finding in findings
        if finding.file_path in relevant_files and finding.status in ACTIONABLE_STATUSES
    )[:OPEN_FINDING_LIMIT]


def _finding_payload(finding: FindingRow) -> dict[str, str]:
    return {
        "id": finding.id,
        "rule_id": finding.rule_id,
        "file_path": finding.file_path,
        "severity": finding.severity,
    }


def _next_tools(
    relevant_symbols: tuple[str, ...],
    open_findings: tuple[dict[str, str], ...],
    *,
    freshness: FreshnessMetadata,
    has_results: bool,
) -> tuple[str, ...]:
    candidates: list[str] = []
    if relevant_symbols:
        candidates.append(f"get_symbol_context:{relevant_symbols[0]}")
    if open_findings:
        candidates.append(f"get_finding_context:{open_findings[0]['id']}")
    candidates.append("select_tests")
    if not has_results:
        candidates.extend(("search_files", "search_content", "get_repo_map"))
    return next_tools_with_refresh_recovery(
        _dedupe_cap(candidates, limit=6),
        freshness,
    )


def _is_test_path(path: str) -> bool:
    parsed = PurePosixPath(path)
    return parsed.name.startswith("test_") or "tests" in parsed.parts


def _dedupe_cap(items: Iterable[str], limit: int) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return tuple(deduped)
