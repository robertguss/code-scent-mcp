"""Serialize code-health findings to SARIF 2.1.0 and GitHub annotation output.

Pure functions only: they map finding fields (``rule_id``, ``severity``,
``file_path``, evidence line range, ``message``, ``suggested_action``) to the two
adoption formats. SARIF feeds GitHub code scanning; the annotation lines surface
findings inline on pull requests. No I/O, no network — deterministic for a given
finding sequence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NotRequired, TypedDict

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codescent.engine.rules.model import CodeHealthFinding, EvidenceValue

SARIF_SCHEMA_URI: Final = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/"
    "Schemata/sarif-schema-2.1.0.json"
)
SARIF_VERSION: Final = "2.1.0"
_TOOL_NAME: Final = "CodeScent"
_MIN_LINE: Final = 1

# Finding severity -> SARIF result level (SARIF level enum is the smaller set).
_SARIF_LEVEL: Final[dict[str, str]] = {
    "error": "error",
    "warning": "warning",
    "info": "note",
}
# Finding severity -> GitHub workflow-command annotation level.
_GITHUB_LEVEL: Final[dict[str, str]] = {
    "error": "error",
    "warning": "warning",
    "info": "notice",
}
_DEFAULT_LEVEL: Final = "warning"


class _ArtifactLocation(TypedDict):
    uri: str


class _Region(TypedDict):
    startLine: int
    endLine: NotRequired[int]


class _PhysicalLocation(TypedDict):
    artifactLocation: _ArtifactLocation
    region: _Region


class _Location(TypedDict):
    physicalLocation: _PhysicalLocation


class _Message(TypedDict):
    text: str


class _ResultProperties(TypedDict):
    suggestedAction: str
    confidence: float
    confidenceTier: str


class SarifResult(TypedDict):
    ruleId: str
    ruleIndex: int
    level: str
    message: _Message
    locations: list[_Location]
    partialFingerprints: dict[str, str]
    properties: _ResultProperties


class SarifRule(TypedDict):
    id: str
    name: str
    shortDescription: _Message


class _Driver(TypedDict):
    name: str
    rules: list[SarifRule]


class _Tool(TypedDict):
    driver: _Driver


class SarifRun(TypedDict):
    tool: _Tool
    results: list[SarifResult]


# Functional syntax is required: "$schema" is not a valid attribute identifier.
SarifLog = TypedDict(
    "SarifLog",
    {"$schema": str, "version": str, "runs": list[SarifRun]},
)


def findings_to_sarif(findings: Sequence[CodeHealthFinding]) -> SarifLog:
    """Return a SARIF 2.1.0 log for ``findings`` (one run, one tool)."""
    rules, rule_index = _rules_and_index(findings)
    results = [_sarif_result(finding, rule_index) for finding in findings]
    return {
        "$schema": SARIF_SCHEMA_URI,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {"driver": {"name": _TOOL_NAME, "rules": rules}},
                "results": results,
            },
        ],
    }


def findings_to_github_annotations(findings: Sequence[CodeHealthFinding]) -> str:
    """Return newline-joined GitHub workflow-command annotation lines."""
    return "\n".join(_github_annotation_line(finding) for finding in findings)


def _rules_and_index(
    findings: Sequence[CodeHealthFinding],
) -> tuple[list[SarifRule], dict[str, int]]:
    rules: list[SarifRule] = []
    index: dict[str, int] = {}
    for finding in findings:
        if finding.rule_id not in index:
            index[finding.rule_id] = len(rules)
            rules.append(
                {
                    "id": finding.rule_id,
                    "name": finding.rule_id,
                    "shortDescription": {"text": finding.title},
                },
            )
    return rules, index


def _sarif_result(
    finding: CodeHealthFinding,
    rule_index: dict[str, int],
) -> SarifResult:
    start = _start_line(finding.evidence)
    region: _Region = {"startLine": start}
    end = _end_line(finding.evidence, start)
    if end is not None:
        region["endLine"] = end
    return {
        "ruleId": finding.rule_id,
        "ruleIndex": rule_index[finding.rule_id],
        "level": _SARIF_LEVEL.get(finding.severity, _DEFAULT_LEVEL),
        "message": {"text": finding.message},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": finding.file_path},
                    "region": region,
                },
            },
        ],
        "partialFingerprints": {"codescentStableKey": finding.stable_key},
        "properties": {
            "suggestedAction": finding.suggested_action,
            "confidence": finding.confidence,
            "confidenceTier": finding.confidence_tier,
        },
    }


def _github_annotation_line(finding: CodeHealthFinding) -> str:
    level = _GITHUB_LEVEL.get(finding.severity, _DEFAULT_LEVEL)
    file_value = _escape_property(finding.file_path)
    line = _start_line(finding.evidence)
    message = _escape_data(finding.message)
    return f"::{level} file={file_value},line={line}::{message}"


def _start_line(evidence: dict[str, EvidenceValue]) -> int:
    for key in ("start_line", "line"):
        line = _positive_int(evidence.get(key))
        if line is not None:
            return line
    return _MIN_LINE


def _end_line(evidence: dict[str, EvidenceValue], start: int) -> int | None:
    end = _positive_int(evidence.get("end_line"))
    if end is not None and end >= start:
        return end
    return None


def _positive_int(value: EvidenceValue | None) -> int | None:
    # bool is an int subclass; a boolean evidence flag is not a line number.
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= _MIN_LINE else None


def _escape_data(value: str) -> str:
    # GitHub workflow-command data escaping (message body).
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(value: str) -> str:
    # Property values additionally escape the field/line delimiters.
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")
