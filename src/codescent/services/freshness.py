from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from codescent.core.paths import resolve_repo_root
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService
from codescent.services.status import RepoStatusService

if TYPE_CHECKING:
    from pathlib import Path

type AdvisoryConfidence = Literal["high", "medium", "low"]

CHANGED_FILE_LIMIT: Final = 20
SCAN_RECOVERY_TOOL: Final = "scan_code_health"
STATE_DIR_NAME: Final = ".codescent"
DATABASE_NAME: Final = "index.sqlite"


@dataclass(frozen=True, slots=True)
class FreshnessMetadata:
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None = None
    bootstrap_disabled: bool = False

    @property
    def confidence(self) -> AdvisoryConfidence:
        if self.refresh_error is not None or self.bootstrap_disabled:
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
        if self.bootstrap_disabled:
            disabled = "auto_bootstrap is disabled and CodeScent state is missing"
            action = "or stale; run scan_code_health to initialize the index"
            return (f"{disabled} {action}",)
        if self.index_was_stale:
            if self.auto_refreshed:
                return (
                    "index was stale and was automatically refreshed before answering",
                )
            return ("index is stale; automatic refresh was skipped for this lookup",)
        return ()


def ensure_fresh_index(repo_root: Path | str) -> FreshnessMetadata:
    root = resolve_repo_root(repo_root)
    if not ConfigService(root).load().auto_bootstrap:
        return _bootstrap_disabled_freshness(root)

    before = RepoStatusService(root).get_status()
    changed_files = before.changed_files[:CHANGED_FILE_LIMIT]
    if before.index_fresh:
        return FreshnessMetadata(
            index_fresh=True,
            index_was_stale=False,
            auto_refreshed=False,
            changed_files=changed_files,
        )

    try:
        _ = CodeHealthService(root).scan()
    except Exception as exc:  # noqa: BLE001 - tool UX must report refresh failure.
        return FreshnessMetadata(
            index_fresh=False,
            index_was_stale=True,
            auto_refreshed=False,
            changed_files=changed_files,
            refresh_error=f"{type(exc).__name__}: {exc}",
        )

    after = RepoStatusService(root).get_status()
    return FreshnessMetadata(
        index_fresh=after.index_fresh,
        index_was_stale=True,
        auto_refreshed=True,
        changed_files=changed_files,
    )


def _bootstrap_disabled_freshness(root: Path) -> FreshnessMetadata:
    # ponytail: opt-out path must never create .codescent/ — read existing state
    # only, never initialize_storage when the index is absent.
    if not (root / STATE_DIR_NAME / DATABASE_NAME).exists():
        return FreshnessMetadata(
            index_fresh=False,
            index_was_stale=True,
            auto_refreshed=False,
            changed_files=(),
            bootstrap_disabled=True,
        )
    status = RepoStatusService(root).get_status()
    return FreshnessMetadata(
        index_fresh=status.index_fresh,
        index_was_stale=not status.index_fresh,
        auto_refreshed=False,
        changed_files=status.changed_files[:CHANGED_FILE_LIMIT],
        bootstrap_disabled=not status.index_fresh,
    )


def next_tools_with_refresh_recovery(
    tools: tuple[str, ...],
    freshness: FreshnessMetadata,
) -> tuple[str, ...]:
    if freshness.refresh_error is None and not freshness.bootstrap_disabled:
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
    constraint_dropped: bool = False,
) -> AdvisoryConfidence:
    if not has_results:
        return "low"
    # A dropped constraint token means the scope the caller asked for was not
    # fully applied, so the results may be broader than intended — cap the
    # confidence so the model does not over-trust them (F2).
    if constraint_dropped:
        return "medium"
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
