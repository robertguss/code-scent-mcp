from pathlib import Path

from codescent.services.code_health import CodeHealthService
from codescent.services.explain import (
    EXPLAIN_SNIPPET_LINE_CAP,
    MAX_SNIPPET_CHARS,
    ExplainService,
)
from codescent.services.findings import FindingsService


def _repo_with_dead_code(
    tmp_path: Path,
    *,
    body_lines: int,
    line_width: int = 8,
) -> Path:
    repo = tmp_path / "repo"
    module = repo / "pkg" / "mod.py"
    module.parent.mkdir(parents=True)
    filler = "x" * line_width
    body = "\n".join(f"    # {filler} {index}" for index in range(body_lines))
    _ = module.write_text(f"def unused_helper() -> int:\n{body}\n    return 0\n")
    return repo


def _dead_code_finding_id(repo: Path) -> str:
    _ = CodeHealthService(repo).scan()
    findings = FindingsService(repo).get_smell_report().findings
    for finding in findings:
        if finding.rule_id == "python.dead_code_candidate":
            return finding.id
    msg = "fixture did not produce a dead_code_candidate finding"
    raise AssertionError(msg)


def test_explain_payload_has_snippet_why_and_fix(tmp_path: Path) -> None:
    repo = _repo_with_dead_code(tmp_path, body_lines=4)
    finding_id = _dead_code_finding_id(repo)

    explanation = ExplainService(repo).explain_finding(finding_id)

    # why = the finding message; fix = the suggested action.
    assert "unused_helper" in explanation.why
    assert explanation.fix
    # bounded source snippet anchored at the finding, includes the def line.
    assert "def unused_helper" in str(explanation.snippet["source"])
    assert explanation.snippet["start_line"] == 1
    assert explanation.snippet["path"] == "pkg/mod.py"
    assert explanation.snippet_truncated is False
    # confidence tier + provenance present (from U7).
    assert explanation.confidence_tier in {"verified", "heuristic"}
    assert explanation.provenance["rule_id"] == explanation.rule_id


def test_oversized_source_is_line_clipped_not_dumped(tmp_path: Path) -> None:
    body_lines = EXPLAIN_SNIPPET_LINE_CAP + 40
    repo = _repo_with_dead_code(tmp_path, body_lines=body_lines)
    finding_id = _dead_code_finding_id(repo)

    explanation = ExplainService(repo).explain_finding(finding_id)

    start = explanation.snippet["start_line"]
    end = explanation.snippet["end_line"]
    assert isinstance(start, int)
    assert isinstance(end, int)
    # The unused function spans far more lines than the cap, yet the snippet is
    # clipped to the line cap rather than dumping the whole symbol.
    span = end - start + 1
    assert span == EXPLAIN_SNIPPET_LINE_CAP
    source = str(explanation.snippet["source"])
    assert source.count("\n") + 1 == EXPLAIN_SNIPPET_LINE_CAP
    assert len(source) <= MAX_SNIPPET_CHARS


def test_oversized_source_is_char_clipped_not_dumped(tmp_path: Path) -> None:
    # Wide lines: even within the line cap the raw source exceeds the char cap,
    # so the snippet string is truncated to the cap rather than dumped.
    repo = _repo_with_dead_code(
        tmp_path,
        body_lines=EXPLAIN_SNIPPET_LINE_CAP + 5,
        line_width=300,
    )
    finding_id = _dead_code_finding_id(repo)

    explanation = ExplainService(repo).explain_finding(finding_id)

    source = str(explanation.snippet["source"])
    assert explanation.snippet_truncated is True
    assert len(source) == MAX_SNIPPET_CHARS
