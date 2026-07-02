"""Content-hash scan cache.

Persists the last scan's rule-pack findings under ``.codescent/`` keyed by a
fingerprint of the repo's per-file content hashes (plus git working-tree status,
the resolved config, and an engine-version tag). When the fingerprint is
unchanged, a scan reuses the cached findings verbatim instead of re-running the
rule packs, so a warm scan is byte-identical to a cold one for the same repo
state. No schema bump: this is pure ``.codescent/`` state (rebuildable, ignored
by git).

The fingerprint hashes every file the enabled packs read: the language
inventory's ``.py``/``.ts``/``.js`` hashes plus, via ``pack_input_hashes``, the
Go and generic-fallback packs' own file sets (which the inventory does not map).

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

from codescent.engine.packs import GO_LANGUAGE_PACK
from codescent.engine.packs_generic import generic_pack_files
from codescent.engine.packs_go import go_pack_files
from codescent.engine.rules.model import CodeHealthFinding
from codescent.engine.source_read import read_source_bytes
from codescent.storage import state_path

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from codescent.core.models import ProjectConfig
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


def pack_input_hashes(
    repo_root: Path,
    config: ProjectConfig,
) -> dict[str, str]:
    """Content hashes of files scanned by packs the language inventory omits.

    ``compute_fingerprint`` keys on the language inventory's per-file hashes
    (``.py``/``.ts``/``.js``). The Go and generic-fallback packs walk their own
    files, so without hashing them here a change to a ``.go`` or generic file
    would be invisible to the fingerprint and a stale scan could be served.
    Hash exactly the files those enabled packs read.
    """
    extra: dict[str, str] = {}
    if GO_LANGUAGE_PACK in config.language_packs:
        for relative in go_pack_files(repo_root, config):
            extra[relative] = _content_hash(repo_root / relative)
    if config.generic_fallback:
        for relative in generic_pack_files(repo_root, config):
            extra[relative] = _content_hash(repo_root / relative)
    return extra


def _content_hash(path: Path) -> str:
    info = read_source_bytes(path)
    if info.content is None:
        # Oversized/unreadable: the packs skip the body, but a size change should
        # still invalidate the cache.
        return f"oversized:{info.size_bytes}"
    return hashlib.sha256(info.content).hexdigest()


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
        # Route through the state-write choke point: state_dir is <repo>/.codescent,
        # so its parent is the repo root (F9 containment invariant).
        return state_path(self.state_dir.parent, CACHE_FILENAME)

    def load(self) -> CachedScan | None:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError:
            return None
        return self._decode(raw)

    def _decode(self, raw: str) -> CachedScan | None:
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
        try:
            findings = tuple(_deserialize(item) for item in items)
        except (KeyError, TypeError, ValueError):
            # A structurally-corrupt entry that still passed the type guards
            # above must degrade to a cold recompute, never crash the scan.
            logger.warning("scan cache entry corrupt, ignoring: %s", self.path)
            return None
        return CachedScan(
            fingerprint=fingerprint,
            file_hashes=cast("dict[str, str]", files),
            findings=findings,
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
        # A cache write failure (disk full, read-only fs) must not discard a
        # scan whose findings are already computed: log and return them.
        try:
            self.state_dir.mkdir(exist_ok=True)
            # Atomic write: a crash mid-write must not poison the next scan.
            tmp = self.path.with_suffix(".json.tmp")
            _ = tmp.write_text(
                json.dumps(record, sort_keys=True, indent=2),
                encoding="utf-8",
            )
            _ = tmp.replace(self.path)
        except OSError:
            logger.warning("scan cache write failed, skipping: %s", self.path)
