from __future__ import annotations

import re
from typing import TYPE_CHECKING

from codescent.engine.rules.model import CodeHealthFinding
from codescent.services.sarif import (
    SARIF_SCHEMA_URI,
    SARIF_VERSION,
    findings_to_github_annotations,
    findings_to_sarif,
)
from tests.sarif_support import validate_sarif

if TYPE_CHECKING:
    from codescent.engine.rules.model import EvidenceValue, Provenance

_GITHUB_LINE = re.compile(r"^::(error|warning|notice) file=[^,]+,line=\d+::.*$")


def _finding(  # noqa: PLR0913
    *,
    rule_id: str,
    title: str,
    message: str,
    file_path: str,
    severity: str,
    stable_key: str,
    evidence: dict[str, EvidenceValue] | None = None,
    symbol: str | None = None,
    confidence: float = 0.8,
    suggested_action: str = "Refactor.",
    confidence_tier: str = "verified",
) -> CodeHealthFinding:
    provenance: Provenance = {"rule_id": rule_id, "symbol_resolved": symbol is not None}
    return CodeHealthFinding(
        id=stable_key,
        stable_key=stable_key,
        rule_id=rule_id,
        title=title,
        message=message,
        file_path=file_path,
        symbol=symbol,
        severity=severity,
        confidence=confidence,
        evidence=evidence if evidence is not None else {},
        suggested_action=suggested_action,
        confidence_tier=confidence_tier,
        provenance=provenance,
    )


def _golden_findings() -> list[CodeHealthFinding]:
    return [
        _finding(
            rule_id="python.large_function",
            title="Large function",
            message="Function 'process' has 30 statements.",
            file_path="src/pkg/config.py",
            severity="warning",
            stable_key="python.large_function:abc123",
            evidence={"start_line": 10, "end_line": 42, "line_count": 30},
            symbol="process",
            confidence=0.8,
            suggested_action="Split process into smaller units.",
            confidence_tier="verified",
        ),
        _finding(
            rule_id="python.todo_cluster",
            title="TODO cluster",
            message="3 TODO/FIXME markers in module.",
            file_path="src/pkg/utils.py",
            severity="info",
            stable_key="python.todo_cluster:def456",
            evidence={"line": 5},
            symbol=None,
            confidence=0.5,
            suggested_action="Resolve or ticket the markers.",
            confidence_tier="heuristic",
        ),
    ]


def test_findings_to_sarif_matches_golden_and_validates() -> None:
    document = findings_to_sarif(_golden_findings())

    expected = {
        "$schema": SARIF_SCHEMA_URI,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "CodeScent",
                        "rules": [
                            {
                                "id": "python.large_function",
                                "name": "python.large_function",
                                "shortDescription": {"text": "Large function"},
                            },
                            {
                                "id": "python.todo_cluster",
                                "name": "python.todo_cluster",
                                "shortDescription": {"text": "TODO cluster"},
                            },
                        ],
                    },
                },
                "results": [
                    {
                        "ruleId": "python.large_function",
                        "ruleIndex": 0,
                        "level": "warning",
                        "message": {"text": "Function 'process' has 30 statements."},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "src/pkg/config.py"},
                                    "region": {"startLine": 10, "endLine": 42},
                                },
                            },
                        ],
                        "partialFingerprints": {
                            "codescentStableKey": "python.large_function:abc123",
                        },
                        "properties": {
                            "suggestedAction": "Split process into smaller units.",
                            "confidence": 0.8,
                            "confidenceTier": "verified",
                        },
                    },
                    {
                        "ruleId": "python.todo_cluster",
                        "ruleIndex": 1,
                        "level": "note",
                        "message": {"text": "3 TODO/FIXME markers in module."},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "src/pkg/utils.py"},
                                    "region": {"startLine": 5},
                                },
                            },
                        ],
                        "partialFingerprints": {
                            "codescentStableKey": "python.todo_cluster:def456",
                        },
                        "properties": {
                            "suggestedAction": "Resolve or ticket the markers.",
                            "confidence": 0.5,
                            "confidenceTier": "heuristic",
                        },
                    },
                ],
            },
        ],
    }

    assert document == expected
    validate_sarif(document)


def test_findings_to_github_annotations_matches_golden() -> None:
    output = findings_to_github_annotations(_golden_findings())

    assert output == (
        "::warning file=src/pkg/config.py,line=10::"
        "Function 'process' has 30 statements.\n"
        "::notice file=src/pkg/utils.py,line=5::3 TODO/FIXME markers in module."
    )
    for line in output.splitlines():
        assert _GITHUB_LINE.fullmatch(line) is not None


def test_github_annotation_escapes_delimiters_and_message() -> None:
    finding = _finding(
        rule_id="python.x",
        title="X",
        message="50% done\nsee notes",
        file_path="src/a,b:c.py",
        severity="warning",
        stable_key="python.x:1",
        evidence={"line": 7},
    )

    line = findings_to_github_annotations([finding])

    assert line == "::warning file=src/a%2Cb%3Ac.py,line=7::50%25 done%0Asee notes"


def test_line_range_defaults_to_one_when_evidence_lacks_lines() -> None:
    finding = _finding(
        rule_id="python.x",
        title="X",
        message="m",
        file_path="src/x.py",
        severity="warning",
        stable_key="python.x:2",
        evidence={"line_count": 9},
    )

    document = findings_to_sarif([finding])
    region = document["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
        "region"
    ]

    assert region["startLine"] == 1
    assert "endLine" not in region
    assert findings_to_github_annotations([finding]).endswith(",line=1::m")


def test_empty_findings_produce_empty_sarif_and_annotations() -> None:
    document = findings_to_sarif([])

    assert document["runs"][0]["results"] == []
    assert document["runs"][0]["tool"]["driver"]["rules"] == []
    assert findings_to_github_annotations([]) == ""
    validate_sarif(document)
