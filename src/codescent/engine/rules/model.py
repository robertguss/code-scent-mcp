from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

type EvidenceValue = int | float | str | bool
type ProvenanceValue = str | bool
type Provenance = dict[str, ProvenanceValue]

CONFIDENCE_TIER_VERIFIED: Final = "verified"
CONFIDENCE_TIER_HEURISTIC: Final = "heuristic"

# Rule-id prefixes whose findings come from the Python AST packs, which resolve
# concrete symbols. Everything else (typescript./react./next.) is regex-derived
# and can therefore only ever be heuristic (the TS pack is regex, not
# tree-sitter — corrected per code audit).
_AST_RULE_PREFIXES: Final = ("python.", "architecture.")


@dataclass(frozen=True, slots=True)
class CodeHealthFinding:
    id: str
    stable_key: str
    rule_id: str
    title: str
    message: str
    file_path: str
    symbol: str | None
    severity: str
    confidence: float
    evidence: dict[str, EvidenceValue]
    suggested_action: str
    confidence_tier: str
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class FindingSpec:
    rule_id: str
    title: str
    message: str
    file_path: str
    symbol: str | None
    severity: str
    confidence: float
    evidence: dict[str, EvidenceValue]
    suggested_action: str
    # Optional overrides; left None so every existing rule call site is unchanged
    # and build_finding() derives a deterministic default.
    confidence_tier: str | None = None
    provenance: Provenance | None = None


def build_finding(spec: FindingSpec) -> CodeHealthFinding:
    stable_key = _stable_key(spec.rule_id, spec.file_path, spec.symbol, spec.evidence)
    # tier/provenance are derived metadata, deliberately NOT folded into
    # stable_key (identity must not depend on them).
    confidence_tier = spec.confidence_tier or derive_confidence_tier(
        spec.rule_id,
        spec.symbol,
    )
    provenance = spec.provenance or derive_provenance(spec.rule_id, spec.symbol)
    return CodeHealthFinding(
        id=stable_key,
        stable_key=stable_key,
        rule_id=spec.rule_id,
        title=spec.title,
        message=spec.message,
        file_path=spec.file_path,
        symbol=spec.symbol,
        severity=spec.severity,
        confidence=spec.confidence,
        evidence=spec.evidence,
        suggested_action=spec.suggested_action,
        confidence_tier=confidence_tier,
        provenance=provenance,
    )


def derive_confidence_tier(rule_id: str, symbol: str | None) -> str:
    """Return ``verified`` only when an AST pack resolved a concrete symbol.

    Regex/TS-pack findings and symbol-less (file-level) findings are heuristic.
    """
    if _resolution_source(rule_id) == "ast" and symbol is not None:
        return CONFIDENCE_TIER_VERIFIED
    return CONFIDENCE_TIER_HEURISTIC


def derive_provenance(rule_id: str, symbol: str | None) -> Provenance:
    return {
        "rule_id": rule_id,
        "language": _provenance_language(rule_id),
        "resolution": _resolution_source(rule_id),
        "symbol_resolved": symbol is not None,
    }


def _resolution_source(rule_id: str) -> str:
    return "ast" if rule_id.startswith(_AST_RULE_PREFIXES) else "regex"


def _provenance_language(rule_id: str) -> str:
    return "python" if rule_id.startswith(_AST_RULE_PREFIXES) else "typescript"


def _stable_key(
    rule_id: str,
    file_path: str,
    symbol: str | None,
    evidence: dict[str, EvidenceValue],
) -> str:
    fingerprint = "|".join(
        f"{key}={value}"
        for key, value in sorted(evidence.items())
        if key
        not in {
            "line_count",
            "count",
            "threshold",
            "depth",
            "import_count",
            # Relative-threshold stats depend on the whole-repo distribution, so
            # they must not enter a finding's identity (adding an unrelated file
            # would otherwise re-key existing outlier findings).
            "repo_median",
            "repo_q3",
            "outlier_cutoff",
            "sample_size",
            "absolute_threshold",
        }
    )
    raw = f"{rule_id}|{file_path}|{symbol or ''}|{fingerprint}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"{rule_id}:{digest}"
