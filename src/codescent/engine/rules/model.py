from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

type EvidenceValue = int | float | str | bool
type ProvenanceValue = str | bool
type Provenance = dict[str, ProvenanceValue]

# `confidence_tier` and `confidence` are two ORTHOGONAL axes, by design:
#   - tier       = how the finding was *derived* -- "verified" iff an AST pack
#                  resolved a concrete symbol, else "heuristic" (regex-derived).
#   - confidence = how *strong* the finding signal is (0.0-1.0).
# They do not track each other. A `"verified"` finding with `confidence: 0.6`
# is valid and meaningful ("the AST is sure this symbol is real; we are only
# moderately sure it is a real problem"), NOT a contradiction to normalize away.
# See test_scan_cache / test_finding_confidence_e2e, which assert this pairing.
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


# Evidence keys deliberately EXCLUDED from a finding's identity. The stable_key
# must survive *benign* edits -- inserting lines above the finding, reformatting,
# and growing/shrinking the body -- so the lifecycle, the ratchet baseline, and
# the verification ledger all stay attached to the same logical finding across
# scans. Two classes of volatile data are dropped:
#   1. Size / count / threshold magnitudes: a finding is "the same long function"
#      whether it is 60 or 65 lines, so its measured size must not re-key it.
#   2. Absolute source positions: ``start_line``/``end_line`` (dead_code),
#      ``line`` (architecture), and the ``path:start-end:name`` ranges inside
#      ``locations`` (structural_duplicates) all shift when unrelated lines are
#      inserted above the finding -- position is not identity. (Audit-correction:
#      these line-position keys previously leaked into the digest and re-keyed
#      dead_code/architecture/duplicate findings on a mere line shift.)
# What REMAINS folded is the finding's *substance* -- the offending literal, the
# duplicate-cluster content ``fingerprint``, the import-cycle path/members, the
# architecture layer + imported module, the dead-symbol ``kind``. Changing those
# is a genuinely different finding, so a rename or a different violation
# legitimately yields a new identity (intended, not a bug).
_VOLATILE_EVIDENCE_KEYS: Final = frozenset(
    {
        "line_count",
        "count",
        "threshold",
        "depth",
        "import_count",
        "repo_median",
        "repo_q3",
        "outlier_cutoff",
        "sample_size",
        "absolute_threshold",
        "start_line",
        "end_line",
        "line",
        "locations",
    },
)


def _stable_key(
    rule_id: str,
    file_path: str,
    symbol: str | None,
    evidence: dict[str, EvidenceValue],
) -> str:
    """Return content-anchored finding identity (``rule_id:digest``).

    Hashes ``rule_id | file_path | symbol | fingerprint(evidence)`` where the
    fingerprint folds in only the *stable substance* of the evidence;
    ``_VOLATILE_EVIDENCE_KEYS`` (sizes, counts, thresholds, and absolute line
    positions) are excluded. Identity therefore survives line shifts and
    reformatting, but legitimately changes on a rename or a different violation.
    """
    fingerprint = "|".join(
        f"{key}={value}"
        for key, value in sorted(evidence.items())
        if key not in _VOLATILE_EVIDENCE_KEYS
    )
    raw = f"{rule_id}|{file_path}|{symbol or ''}|{fingerprint}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"{rule_id}:{digest}"
