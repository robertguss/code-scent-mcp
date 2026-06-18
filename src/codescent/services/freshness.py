from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from codescent.services.code_health import CodeHealthService
from codescent.services.status import RepoStatusService

if TYPE_CHECKING:
    from pathlib import Path

type AdvisoryConfidence = Literal["high", "medium", "low"]

CHANGED_FILE_LIMIT: Final = 20
SCAN_RECOVERY_TOOL: Final = "scan_code_health"


@dataclass(frozen=True, slots=True)
class FreshnessMetadata:
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None = None

    @property
    def confidence(self) -> AdvisoryConfidence:
        if self.refresh_error is not None:
            return "low"
        if self.index_was_stale:
            return "medium"
        return "high"

    @property
    def warnings(self) -> tuple[str, ...]:
        if self.refresh_error is not None:
            prefix = "index stale; automatic refresh failed; run scan_code_health"
            suffix = "before trusting missing or low-confidence results"
            return (f"{prefix} {suffix}",)
        if self.index_was_stale:
            if self.auto_refreshed:
                return (
                    "index was stale and was automatically refreshed before answering",
                )
            return ("index is stale; automatic refresh was skipped for this lookup",)
        return ()


def ensure_fresh_index(repo_root: Path | str) -> FreshnessMetadata:
    before = RepoStatusService(repo_root).get_status()
    changed_files = before.changed_files[:CHANGED_FILE_LIMIT]
    if before.index_fresh:
        return FreshnessMetadata(
            index_fresh=True,
            index_was_stale=False,
            auto_refreshed=False,
            changed_files=changed_files,
        )

    try:
        _ = CodeHealthService(repo_root).scan()
    except Exception as exc:  # noqa: BLE001 - tool UX must report refresh failure.
        return FreshnessMetadata(
            index_fresh=False,
            index_was_stale=True,
            auto_refreshed=False,
            changed_files=changed_files,
            refresh_error=f"{type(exc).__name__}: {exc}",
        )

    after = RepoStatusService(repo_root).get_status()
    return FreshnessMetadata(
        index_fresh=after.index_fresh,
        index_was_stale=True,
        auto_refreshed=True,
        changed_files=changed_files,
    )


def next_tools_with_refresh_recovery(
    tools: tuple[str, ...],
    freshness: FreshnessMetadata,
) -> tuple[str, ...]:
    if freshness.refresh_error is None:
        return tools
    return _dedupe((SCAN_RECOVERY_TOOL, *tools))


def no_result_warning(*, result_kind: str) -> str:
    return (
        f"no {result_kind} found; if this miss matters, try a narrower query, "
        "search_files, search_content, or get_repo_map"
    )


def confidence_for_results(
    *,
    has_results: bool,
    freshness: FreshnessMetadata | None = None,
) -> AdvisoryConfidence:
    if not has_results:
        return "low"
    if freshness is None:
        return "high"
    return freshness.confidence


def warnings_for_results(
    *,
    has_results: bool,
    result_kind: str,
    freshness: FreshnessMetadata | None = None,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if freshness is not None:
        warnings.extend(freshness.warnings)
    if not has_results:
        warnings.append(no_result_warning(result_kind=result_kind))
    return tuple(warnings)


def _dedupe(items: tuple[str, ...]) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return tuple(deduped)
