"""Auto-bootstrap CodeScent's own state on first use.

A thin, idempotent helper invoked from the shared service entry path
(``freshness.ensure_fresh_index``) and from ``start_task``. When ``.codescent/``
state is missing or the index is stale it runs the minimal init -> index -> scan
(writing ONLY under ``.codescent/``), then reports a bounded note describing what
ran. Present-and-fresh is a no-op. ``auto_bootstrap = false`` opts out and returns
"run init" guidance instead of doing any work.

Invariants (proven by ``scripts/prove_auto_bootstrap.py``):
- writes only under ``.codescent/`` (never analyzed source);
- performs no network I/O;
- reuses the existing repo_index / scan / freshness services (no reimplementation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, TypedDict

from codescent.core.paths import resolve_repo_root
from codescent.services.config import ConfigService
from codescent.services.freshness import (
    DATABASE_NAME,
    STATE_DIR_NAME,
    FreshnessMetadata,
    ensure_fresh_index,
)

if TYPE_CHECKING:
    from pathlib import Path

INIT_INDEX_SCAN: Final = ("init", "index", "scan")
INDEX_SCAN: Final = ("index", "scan")
DISABLED_GUIDANCE: Final = (
    "auto_bootstrap is disabled; run scan_code_health to initialize CodeScent state",
)
FAILED_GUIDANCE: Final = ("index auto-refresh failed; run scan_code_health and retry",)


class BootstrapNote(TypedDict):
    bootstrapped: bool
    ran: tuple[str, ...]
    reason: str
    guidance: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    bootstrapped: bool
    ran: tuple[str, ...]
    reason: str
    guidance: tuple[str, ...]
    freshness: FreshnessMetadata

    def note(self) -> BootstrapNote:
        return {
            "bootstrapped": self.bootstrapped,
            "ran": self.ran,
            "reason": self.reason,
            "guidance": self.guidance,
        }


def ensure_bootstrapped(repo_root: Path | str) -> BootstrapResult:
    """Ensure CodeScent state exists and is fresh, reporting what ran.

    Idempotent: present-and-fresh state is a no-op. Honors the ``auto_bootstrap``
    config opt-out. Delegates the actual init -> index -> scan to the existing
    freshness/scan services, so nothing is reimplemented here.
    """
    root = resolve_repo_root(repo_root)
    auto_bootstrap = ConfigService(root).load().auto_bootstrap
    index_existed = (root / STATE_DIR_NAME / DATABASE_NAME).exists()
    freshness = ensure_fresh_index(root)
    return _classify(
        auto_bootstrap=auto_bootstrap,
        index_existed=index_existed,
        freshness=freshness,
    )


def _classify(
    *,
    auto_bootstrap: bool,
    index_existed: bool,
    freshness: FreshnessMetadata,
) -> BootstrapResult:
    if not auto_bootstrap:
        guidance = () if freshness.index_fresh else DISABLED_GUIDANCE
        return BootstrapResult(
            bootstrapped=False,
            ran=(),
            reason="disabled",
            guidance=guidance,
            freshness=freshness,
        )
    if freshness.refresh_error is not None:
        return BootstrapResult(
            bootstrapped=False,
            ran=(),
            reason="failed",
            guidance=FAILED_GUIDANCE,
            freshness=freshness,
        )
    if not index_existed:
        return BootstrapResult(
            bootstrapped=True,
            ran=INIT_INDEX_SCAN,
            reason="created",
            guidance=(),
            freshness=freshness,
        )
    if freshness.auto_refreshed:
        return BootstrapResult(
            bootstrapped=True,
            ran=INDEX_SCAN,
            reason="refreshed",
            guidance=(),
            freshness=freshness,
        )
    return BootstrapResult(
        bootstrapped=False,
        ran=(),
        reason="fresh",
        guidance=(),
        freshness=freshness,
    )
