from __future__ import annotations

from typing import TYPE_CHECKING, Final

from codescent.core.paths import resolve_repo_root
from codescent.engine.packs_ts import TS_EXTENSIONS
from codescent.engine.rules.model import CodeHealthFinding, FindingSpec, build_finding

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from codescent.core.models import ProjectConfig
    from codescent.services.git import FileAuthorChurn

PYTHON_KNOWLEDGE_SILO_RULE_ID: Final = "python.knowledge_silo"
TYPESCRIPT_KNOWLEDGE_SILO_RULE_ID: Final = "typescript.knowledge_silo"
# A file must be both high-churn AND dominated by one author to be a silo; either
# alone is normal. Tuned so small/young histories self-quiet (no false alarms).
MIN_SILO_CHURN: Final = 5
SILO_DOMINANCE_THRESHOLD: Final = 0.8
SINGLE_AUTHOR_COUNT: Final = 1
# HIGH when one author owns the whole file; LOW when ownership is concentrated
# but shared (the heuristic is noisier, so it stays a hint, not a warning).
HIGH_CONFIDENCE: Final = 0.9
LOW_CONFIDENCE: Final = 0.5
MAX_KNOWLEDGE_SILO_FINDINGS: Final = 100
_PYTHON_SUFFIXES: Final = (".py", ".pyi")


def scan_knowledge_silos(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
) -> tuple[CodeHealthFinding, ...]:
    """Flag high-churn, single-/dominant-author files (knowledge silos).

    Self-disables (returns ``()``) when there is no git history, so non-git
    trees and shallow repos produce nothing. Deterministic for a fixed history.
    """
    _ = config
    # ponytail: function-scoped import. The bus-factor signal is inherently
    # git-derived, so this engine rule must reach services/git.py -- but
    # services/__init__ eagerly imports engine.packs, so a module-level import
    # deadlocks. Importing at call time (the codebase's own cycle-break) is safe:
    # engine.packs is fully loaded by then. Hence engine cannot import git at
    # module scope, which is exactly why import_cycles degrades to size instead.
    from codescent.services.git import git_author_churn  # noqa: PLC0415

    repo_root = resolve_repo_root(root)
    return build_knowledge_silo_findings(git_author_churn(repo_root))


def build_knowledge_silo_findings(
    churn_by_path: Mapping[str, FileAuthorChurn],
) -> tuple[CodeHealthFinding, ...]:
    """Build silo findings from per-file author concentration (pure)."""
    findings: list[CodeHealthFinding] = []
    for path, stats in sorted(churn_by_path.items()):
        finding = _silo_finding(path, stats)
        if finding is not None:
            findings.append(finding)
        if len(findings) >= MAX_KNOWLEDGE_SILO_FINDINGS:
            break
    return tuple(findings)


def _silo_finding(path: str, stats: FileAuthorChurn) -> CodeHealthFinding | None:
    rule_id = _rule_id_for_path(path)
    if rule_id is None:
        return None
    if (
        stats.churn < MIN_SILO_CHURN
        or stats.top_author_share < SILO_DOMINANCE_THRESHOLD
    ):
        return None
    single_author = stats.author_count <= SINGLE_AUTHOR_COUNT
    confidence = HIGH_CONFIDENCE if single_author else LOW_CONFIDENCE
    language = "python" if rule_id == PYTHON_KNOWLEDGE_SILO_RULE_ID else "typescript"
    share_pct = round(stats.top_author_share * 100)
    return build_finding(
        FindingSpec(
            rule_id=rule_id,
            title="Knowledge silo",
            message=(
                f"{path} is high-churn ({stats.churn} recent commits) with "
                f"{share_pct}% authored by one contributor across "
                f"{stats.author_count} distinct author(s) — a bus-factor risk."
            ),
            file_path=path,
            symbol=None,
            severity="info",
            confidence=confidence,
            evidence={
                "churn": stats.churn,
                "top_author_share": round(stats.top_author_share, 2),
                "author_count": stats.author_count,
                # ``threshold`` is excluded from stable_key identity by design.
                "threshold": SILO_DOMINANCE_THRESHOLD,
            },
            suggested_action=(
                "Spread ownership: pair on or review changes to this file, add "
                "docs, or schedule a knowledge-transfer session to raise the "
                "bus factor."
            ),
            # Explicit git provenance: derive_provenance would mislabel a
            # python.* rule as AST-resolved, but this signal is git-derived.
            provenance={
                "rule_id": rule_id,
                "language": language,
                "resolution": "git",
                "symbol_resolved": False,
            },
        ),
    )


def _rule_id_for_path(path: str) -> str | None:
    if path.endswith(_PYTHON_SUFFIXES):
        return PYTHON_KNOWLEDGE_SILO_RULE_ID
    if path.endswith(TS_EXTENSIONS):
        return TYPESCRIPT_KNOWLEDGE_SILO_RULE_ID
    return None
