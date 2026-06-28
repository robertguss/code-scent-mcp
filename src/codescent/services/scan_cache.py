"""Content-hash scan cache (plan unit U16).

Persists the last scan's rule-pack findings under ``.codescent/`` keyed by a
fingerprint of the repo's per-file content hashes (plus git working-tree status,
the resolved config, and an engine-version tag). When the fingerprint is
unchanged, a scan reuses the cached findings verbatim instead of re-running the
rule packs, so a warm scan is byte-identical to a cold one for the same repo
state. No schema bump: this is pure ``.codescent/`` state (rebuildable, ignored
by git).

ponytail: cache keyed by content hashes + git status + config + engine version.
Pure git-history changes (new commits, identical file bytes) are caught by the
clean<->dirty status flip; an amend-in-place that keeps status clean could serve
a stale bus-factor finding -- upgrade path: fold ``git rev-parse HEAD`` into the
fingerprint. Engine code edits without an engine-version bump are also not seen
by the key; ``.codescent/`` is throwaway, so clearing it rebuilds.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from codescent.engine.rules.model import CodeHealthFinding

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from codescent.engine.rules.model import EvidenceValue, Provenance

logger = logging.getLogger(__name__)

CACHE_VERSION = 1
CACHE_FILENAME = "scan_cache.json"


def compute_fingerprint(
    file_hashes: Mapping[str, str],
    *,
    git_status: str,
    config_repr: str,
    engine_version: str,
) -> str:
    """Return a stable hash of every input that can change rule-pack findings."""
    payload = json.dumps(
        {
            "engine_version": engine_version,
            "git_status": git_status,
            "config": config_repr,
            "files": dict(sorted(file_hashes.items())),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def changed_paths(
    cached_files: Mapping[str, str],
    current_files: Mapping[str, str],
) -> tuple[str, ...]:
    """Paths that are new or whose content hash differs from the cached scan."""
    return tuple(
        sorted(
            path
            for path, file_hash in current_files.items()
            if cached_files.get(path) != file_hash
        ),
    )


def _serialize(finding: CodeHealthFinding) -> dict[str, object]:
    return {
        "id": finding.id,
        "stable_key": finding.stable_key,
        "rule_id": finding.rule_id,
        "title": finding.title,
        "message": finding.message,
        "file_path": finding.file_path,
        "symbol": finding.symbol,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "evidence": dict(finding.evidence),
        "suggested_action": finding.suggested_action,
        "confidence_tier": finding.confidence_tier,
        "provenance": dict(finding.provenance),
    }


def _deserialize(data: Mapping[str, object]) -> CodeHealthFinding:
    return CodeHealthFinding(
        id=cast("str", data["id"]),
        stable_key=cast("str", data["stable_key"]),
        rule_id=cast("str", data["rule_id"]),
        title=cast("str", data["title"]),
        message=cast("str", data["message"]),
        file_path=cast("str", data["file_path"]),
        symbol=cast("str | None", data["symbol"]),
        severity=cast("str", data["severity"]),
        confidence=cast("float", data["confidence"]),
        evidence=cast("dict[str, EvidenceValue]", data["evidence"]),
        suggested_action=cast("str", data["suggested_action"]),
        confidence_tier=cast("str", data["confidence_tier"]),
        provenance=cast("Provenance", data["provenance"]),
    )


@dataclass(frozen=True, slots=True)
class CachedScan:
    fingerprint: str
    file_hashes: dict[str, str]
    findings: tuple[CodeHealthFinding, ...]


@dataclass(frozen=True, slots=True)
class ScanCache:
    state_dir: Path

    @property
    def path(self) -> Path:
        return self.state_dir / CACHE_FILENAME

    def load(self) -> CachedScan | None:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            decoded = cast("object", json.loads(raw))
        except json.JSONDecodeError:
            logger.warning("scan cache unreadable, ignoring: %s", self.path)
            return None
        if not isinstance(decoded, dict):
            return None
        record = cast("dict[str, object]", decoded)
        if record.get("version") != CACHE_VERSION:
            return None
        fingerprint = record.get("fingerprint")
        files = record.get("files")
        findings_raw = record.get("findings")
        if (
            not isinstance(fingerprint, str)
            or not isinstance(files, dict)
            or not isinstance(findings_raw, list)
        ):
            return None
        items = cast("list[dict[str, object]]", findings_raw)
        return CachedScan(
            fingerprint=fingerprint,
            file_hashes=cast("dict[str, str]", files),
            findings=tuple(_deserialize(item) for item in items),
        )

    def store(
        self,
        *,
        fingerprint: str,
        file_hashes: Mapping[str, str],
        findings: tuple[CodeHealthFinding, ...],
    ) -> None:
        record = {
            "version": CACHE_VERSION,
            "fingerprint": fingerprint,
            "files": dict(sorted(file_hashes.items())),
            "findings": [_serialize(finding) for finding in findings],
        }
        self.state_dir.mkdir(exist_ok=True)
        # Atomic write: a crash mid-write must not poison the next scan.
        tmp = self.path.with_suffix(".json.tmp")
        _ = tmp.write_text(
            json.dumps(record, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        _ = tmp.replace(self.path)
