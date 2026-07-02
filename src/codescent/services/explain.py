from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from codescent.core.json_decode import JsonObject, JsonScalar, decode_json_object
from codescent.core.paths import resolve_repo_root
from codescent.engine.context import source_range
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository

if TYPE_CHECKING:
    from pathlib import Path

# Bounded snippet caps. A finding's source snippet is clipped to at most this
# many lines (source_range) and this many characters (here) so an explanation is
# always fix-ready but never an unbounded source dump.
EXPLAIN_SNIPPET_LINE_CAP: Final = 40
MAX_SNIPPET_CHARS: Final = 4000

# Returned in place of a source snippet when a finding has no resolvable file
# location. The message and evidence still carry the actionable detail.
_NO_LOCATION_SNIPPET: Final[dict[str, str | int]] = {
    "path": "",
    "start_line": 0,
    "end_line": 0,
    "source": "",
    "note": "no resolvable source location; see message and evidence",
}


@dataclass(frozen=True, slots=True)
class FindingExplanation:
    finding_id: str
    rule_id: str
    file_path: str
    severity: str
    confidence_tier: str
    provenance: JsonObject
    why: str
    evidence: JsonObject
    fix: str
    snippet: dict[str, str | int]
    snippet_truncated: bool
    next_tools: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExplainService:
    repo_root: Path | str

    def explain_finding(
        self,
        finding_id: str,
        *,
        line_cap: int = EXPLAIN_SNIPPET_LINE_CAP,
    ) -> FindingExplanation:
        """Compose one bounded fix-ready explanation: why + fix + a snippet.

        The snippet is read through ``source_range`` (which omits files beyond
        the source-read byte budget) and clipped to ``line_cap`` lines and
        ``MAX_SNIPPET_CHARS`` characters -- never an unbounded source dump.
        """
        finding = _repository(self.repo_root).get_finding(finding_id)
        evidence = decode_json_object(finding.evidence_json)
        start_line, end_line = _line_range(evidence)
        if finding.file_path:
            snippet, truncated = _bounded_snippet(
                resolve_repo_root(self.repo_root),
                finding.file_path,
                start_line=start_line,
                end_line=end_line,
                line_cap=line_cap,
            )
        else:
            # A finding with no resolvable source location (e.g. a generic-pack
            # finding on a non-indexed file not yet rescanned) still has a useful
            # message/evidence/fix. Degrade to a note instead of reading source
            # from an empty path, which would raise and surface as a
            # non-recoverable internal error.
            snippet, truncated = _NO_LOCATION_SNIPPET, False
        return FindingExplanation(
            finding_id=finding.id,
            rule_id=finding.rule_id,
            file_path=finding.file_path,
            severity=finding.severity,
            confidence_tier=finding.confidence_tier,
            provenance=decode_json_object(finding.provenance_json),
            why=finding.message,
            evidence=evidence,
            fix=finding.suggested_action,
            snippet=snippet,
            snippet_truncated=truncated,
            next_tools=("plan_refactor", "suggest_tests"),
        )


def _bounded_snippet(
    repo_root: Path,
    file_path: str,
    *,
    start_line: int,
    end_line: int,
    line_cap: int,
) -> tuple[dict[str, str | int], bool]:
    payload = source_range(
        repo_root,
        file_path,
        start_line=start_line,
        end_line=end_line,
        line_cap=line_cap,
    ).to_payload()
    source = payload["source"]
    if isinstance(source, str) and len(source) > MAX_SNIPPET_CHARS:
        return {**payload, "source": source[:MAX_SNIPPET_CHARS]}, True
    return payload, False


def _line_range(evidence: JsonObject) -> tuple[int, int]:
    anchor = _int_value(evidence.get("start_line")) or _int_value(evidence.get("line"))
    start_line = anchor if anchor and anchor > 0 else 1
    end = _int_value(evidence.get("end_line"))
    end_line = end if end and end >= start_line else start_line
    return start_line, end_line


def _int_value(value: JsonScalar) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _repository(repo_root: Path | str) -> FindingRepository:
    state = initialize_storage(repo_root)
    return FindingRepository(RepositoryStorage(state))
