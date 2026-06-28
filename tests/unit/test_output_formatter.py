from __future__ import annotations

from typing import TYPE_CHECKING, cast

from codescent.core.models import EnvelopeMode, ResponseEnvelope
from codescent.core.output_formatter import format_test_output
from tests.fixtures.headroom_influence_fixtures import build_test_output_fixtures

if TYPE_CHECKING:
    from collections.abc import Mapping


def _item(envelope: ResponseEnvelope, index: int) -> Mapping[str, object]:
    return cast("Mapping[str, object]", envelope.items[index])


def _item_text(envelope: ResponseEnvelope, index: int, key: str) -> str:
    return cast("str", _item(envelope, index)[key])


def _item_int(envelope: ResponseEnvelope, index: int, key: str) -> int:
    return cast("int", _item(envelope, index)[key])


def test_format_test_output_preserves_failure_metadata_before_truncation() -> None:
    fixtures = build_test_output_fixtures()

    failing = format_test_output(fixtures["failing_assertion"])
    traceback = format_test_output(fixtures["traceback_root_cause"])
    environmental = format_test_output(fixtures["environmental_failure"])
    non_utf8_safe = format_test_output(fixtures["non_utf8_safe_text"])
    long_failure = format_test_output(fixtures["very_long_single_line"])

    for envelope, fixture in (
        (failing, fixtures["failing_assertion"]),
        (traceback, fixtures["traceback_root_cause"]),
        (environmental, fixtures["environmental_failure"]),
        (non_utf8_safe, fixtures["non_utf8_safe_text"]),
        (long_failure, fixtures["very_long_single_line"]),
    ):
        first_item = _item(envelope, 0)
        assert first_item["type"] == "failure_details"
        assert first_item["failed_test_names"] == fixture["failed_test_names"]
        assert first_item["rerun_command"] == fixture["rerun_command"]
        assert first_item["deterministic_classification"] == (
            "deterministic" if fixture["deterministic"] else "environmental"
        )
        assert envelope.summary

    assert failing.mode is EnvelopeMode.EXACT
    assert _item_text(failing, 0, "assertion_summary") == "assert 2 == 3"
    assert _item_text(failing, 0, "traceback_root_cause") == "assert 2 == 3"

    traceback_item = _item(traceback, 0)
    assert traceback_item["traceback_root_cause"] == (
        "ValueError: invalid manifest header"
    )
    assert traceback_item["traceback_frames"] == (
        {"file": "tests/test_loader.py", "line": 9, "function": "test_imports"},
        {"file": "src/loader.py", "line": 31, "function": "load_manifest"},
    )
    assert "ValueError: invalid manifest header" in traceback.summary

    assert environmental.mode is EnvelopeMode.EXACT
    assert _item_text(environmental, 0, "deterministic_classification") == (
        "environmental"
    )
    assert "environmental" in environmental.summary
    assert any("environmental" in warning for warning in environmental.warnings)

    assert "\ufffd" in _item_text(non_utf8_safe, 1, "stdout_preview")
    assert any(
        "replacement characters" in warning for warning in non_utf8_safe.warnings
    )

    assert long_failure.mode is EnvelopeMode.TRUNCATED
    assert long_failure.omitted_count > 0
    assert _item_int(long_failure, 1, "stdout_omitted_chars") > 0


def test_format_test_output_summarizes_long_passing_output() -> None:
    fixtures = build_test_output_fixtures()
    long_passing = {
        **fixtures["empty"],
        "name": "long_passing_output",
        "stdout": "x" * 4096,
        "stderr": "",
        "exit_code": 0,
        "deterministic": True,
    }

    envelope = format_test_output(long_passing, result_id="result-123")

    assert envelope.mode is EnvelopeMode.SUMMARIZED
    assert envelope.original_result_id == "result-123"
    assert envelope.retrieval_available is True
    assert envelope.retrieval_hints == ("retrieve_result(result_id='result-123')",)
    first_item = _item(envelope, 0)
    assert first_item["type"] == "passing_output_summary"
    stdout_omitted_chars = _item_int(envelope, 0, "stdout_omitted_chars")
    assert stdout_omitted_chars > 0
    assert envelope.omitted_count == stdout_omitted_chars
    assert "omitted" in envelope.summary
    assert envelope.stats is not None
    assert envelope.stats["token_estimate"] > 0


def test_format_test_output_keeps_empty_output_exact_and_bounded() -> None:
    fixtures = build_test_output_fixtures()

    envelope = format_test_output(fixtures["empty"])

    assert envelope.mode is EnvelopeMode.EXACT
    assert envelope.summary == "Test run completed with no output."
    assert envelope.items == ()
    assert envelope.omitted_count == 0
    assert envelope.retrieval_available is False
    assert envelope.stats == {
        "failed_test_count": 0,
        "relevant_file_count": 0,
        "stdout_chars": 0,
        "stderr_chars": 0,
        "captured_chars": 0,
        "omitted_chars": 0,
        "token_estimate": 0,
        "traceback_frame_count": 0,
    }
