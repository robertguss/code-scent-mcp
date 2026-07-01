from __future__ import annotations

from codescent.engine.rules.model import CodeHealthFinding, FindingSpec, build_finding
from codescent.engine.suppression import (
    finding_candidate_lines,
    is_scan_time_suppressed,
    match_suppressions,
    parse_ignore_directives,
    suppressing_directive,
)


def test_scan_time_suppresses_precision_corpus_for_all_rules() -> None:
    assert is_scan_time_suppressed(
        "python.duplicate_literal",
        "evals/precision_corpus/pkg/x.py",
        is_test=False,
    )
    assert is_scan_time_suppressed(
        "python.assertion_free_test",
        "evals/precision_corpus/pkg/x.py",
        is_test=False,
    )


def test_scan_time_suppresses_noise_rules_in_test_scope() -> None:
    for rule_id in (
        "python.duplicate_literal",
        "generic.duplicate_literal",
        "python.missing_nearby_test",
        "python.large_file",
    ):
        assert is_scan_time_suppressed(rule_id, "tests/test_x.py", is_test=True)


def test_scan_time_keeps_test_quality_rules_in_test_scope() -> None:
    assert not is_scan_time_suppressed(
        "python.assertion_free_test",
        "tests/test_x.py",
        is_test=True,
    )
    assert not is_scan_time_suppressed(
        "python.over_mocked_test",
        "tests/test_x.py",
        is_test=True,
    )


def test_scan_time_keeps_noise_rules_in_source_scope() -> None:
    assert not is_scan_time_suppressed(
        "python.duplicate_literal",
        "src/app.py",
        is_test=False,
    )
    assert not is_scan_time_suppressed(
        "python.large_file",
        "src/app.py",
        is_test=False,
    )


def _finding(
    rule_id: str,
    file_path: str,
    *,
    symbol: str | None = None,
    evidence: dict[str, int | float | str | bool] | None = None,
) -> CodeHealthFinding:
    return build_finding(
        FindingSpec(
            rule_id=rule_id,
            title="title",
            message="message",
            file_path=file_path,
            symbol=symbol,
            severity="info",
            confidence=0.5,
            evidence=evidence or {},
            suggested_action="action",
        ),
    )


# --- parser: comment forms -------------------------------------------------


def test_parses_python_hash_form() -> None:
    (directive,) = parse_ignore_directives(
        ["# codescent: ignore[python.large_file]"],
    )
    assert directive.line == 1
    assert directive.rule_ids == frozenset({"python.large_file"})


def test_parses_typescript_slash_form() -> None:
    (directive,) = parse_ignore_directives(
        ["// codescent: ignore[react.too_many_hooks]"],
    )
    assert directive.rule_ids == frozenset({"react.too_many_hooks"})


def test_parses_bare_form_as_all_rules() -> None:
    (directive,) = parse_ignore_directives(["# codescent: ignore"])
    assert directive.rule_ids == frozenset()
    assert directive.matches_rule("anything.at.all")


def test_parses_multiple_rule_ids() -> None:
    (directive,) = parse_ignore_directives(
        ["# codescent: ignore[python.large_file, python.todo_cluster, react.x]"],
    )
    assert directive.rule_ids == frozenset(
        {"python.large_file", "python.todo_cluster", "react.x"},
    )


def test_parses_inline_trailing_comment_and_keeps_audit_text() -> None:
    (directive,) = parse_ignore_directives(
        ["def big() -> None:  # codescent: ignore[python.large_function]"],
    )
    assert directive.line == 1
    assert directive.rule_ids == frozenset({"python.large_function"})
    assert directive.comment == "# codescent: ignore[python.large_function]"


def test_parses_with_no_space_after_colon() -> None:
    (directive,) = parse_ignore_directives(["# codescent:ignore[r.a]"])
    assert directive.rule_ids == frozenset({"r.a"})


def test_records_correct_line_numbers() -> None:
    directives = parse_ignore_directives(
        ["code", "# codescent: ignore[a]", "more", "# codescent: ignore"],
    )
    assert [d.line for d in directives] == [2, 4]


# --- parser: negative cases ------------------------------------------------


def test_plain_comment_does_not_match() -> None:
    assert parse_ignore_directives(["# just a normal comment"]) == ()


def test_missing_colon_does_not_match() -> None:
    assert parse_ignore_directives(["# codescent ignore[r.a]"]) == ()


def test_ignored_word_does_not_match() -> None:
    assert parse_ignore_directives(["# codescent: ignored stuff"]) == ()


# --- matcher: same-line vs line-above --------------------------------------


def test_directive_on_same_line_matches() -> None:
    (directive,) = parse_ignore_directives(["# codescent: ignore[r.a]"])
    assert suppressing_directive([1], [directive], "r.a") is directive


def test_directive_directly_above_matches() -> None:
    (directive,) = parse_ignore_directives(["# codescent: ignore[r.a]"])
    # comment on line 1, finding on line 2 -> directly above.
    assert suppressing_directive([2], [directive], "r.a") is directive


def test_directive_two_lines_above_does_not_match() -> None:
    (directive,) = parse_ignore_directives(["# codescent: ignore[r.a]"])
    assert suppressing_directive([3], [directive], "r.a") is None


def test_directive_for_other_rule_does_not_match() -> None:
    (directive,) = parse_ignore_directives(["# codescent: ignore[r.a]"])
    assert suppressing_directive([1], [directive], "r.b") is None


def test_bare_directive_matches_any_rule() -> None:
    (directive,) = parse_ignore_directives(["# codescent: ignore"])
    assert suppressing_directive([1], [directive], "r.whatever") is directive


# --- line resolution -------------------------------------------------------


def test_candidate_lines_from_start_line_evidence() -> None:
    finding = _finding(
        "python.dead_code_candidate", "a.py", evidence={"start_line": 12}
    )
    assert finding_candidate_lines(finding, {}) == frozenset({12})


def test_candidate_lines_from_line_evidence() -> None:
    finding = _finding("architecture.layering", "a.py", evidence={"line": 7})
    assert finding_candidate_lines(finding, {}) == frozenset({7})


def test_candidate_lines_from_symbol_resolution() -> None:
    finding = _finding("python.large_function", "a.py", symbol="a.big")
    lines = finding_candidate_lines(finding, {("a.py", "a.big"): 20})
    assert lines == frozenset({20})


def test_file_level_finding_has_no_candidate_lines() -> None:
    finding = _finding("python.large_file", "a.py", evidence={"line_count": 999})
    assert finding_candidate_lines(finding, {}) == frozenset()


# --- end-to-end pure matching ----------------------------------------------


def test_match_suppressions_suppresses_only_the_targeted_finding() -> None:
    suppressed = _finding(
        "python.dead_code_candidate",
        "a.py",
        evidence={"start_line": 2},
    )
    untouched = _finding(
        "python.dead_code_candidate",
        "a.py",
        evidence={"start_line": 9},
    )
    directives = parse_ignore_directives(
        ["# codescent: ignore[python.dead_code_candidate]"],  # line 1 -> covers line 2
    )
    matches = match_suppressions(
        [suppressed, untouched],
        {"a.py": directives},
        {},
    )
    assert set(matches) == {suppressed.stable_key}
    assert matches[suppressed.stable_key].rule_id == "python.dead_code_candidate"
    assert "ignore" in matches[suppressed.stable_key].comment
