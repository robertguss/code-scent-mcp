from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from codescent.core.models import (
    EnvelopeConfidence,
    EnvelopeMode,
    ResponseEnvelope,
)
from codescent.core.preservation import estimate_token_usage

if TYPE_CHECKING:
    from collections.abc import Mapping

_TRACEBACK_FRAME_RE = re.compile(
    r'^\s*File "(?P<file>.+)", line (?P<line>\d+), in (?P<function>.+)$'
)
_MAX_PREVIEW_CHARS = 256


class TestOutputRecord(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    name: str
    failed_test_names: tuple[str, ...] = Field(default_factory=tuple)
    assertion_summary: str | None = None
    traceback_root_cause: str | None = None
    relevant_files: tuple[str, ...] = Field(default_factory=tuple)
    rerun_command: str
    deterministic: bool | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


def format_test_output(
    record: TestOutputRecord | Mapping[str, object],
    *,
    result_id: str | None = None,
) -> ResponseEnvelope:
    test_output = TestOutputRecord.model_validate(record)
    if test_output.exit_code == 0:
        return _empty_or_pass_envelope(test_output, result_id=result_id)

    combined_output = test_output.stdout + test_output.stderr
    token_estimate = estimate_token_usage(combined_output).tokens
    traceback_frames = _extract_traceback_frames(test_output.stderr)
    preserved_item = {
        "type": "failure_details",
        "failed_test_names": test_output.failed_test_names,
        "assertion_summary": test_output.assertion_summary,
        "traceback_root_cause": test_output.traceback_root_cause,
        "traceback_frames": traceback_frames,
        "relevant_files": test_output.relevant_files,
        "rerun_command": test_output.rerun_command,
        "deterministic_classification": _classification_label(test_output),
    }
    items: list[object] = [preserved_item]

    stdout_preview, stdout_omitted = _preview_text(test_output.stdout)
    stderr_preview, stderr_omitted = _preview_text(test_output.stderr)
    omitted_count = stdout_omitted + stderr_omitted
    if combined_output:
        items.append(
            {
                "type": "output_preview",
                "stdout_preview": stdout_preview,
                "stderr_preview": stderr_preview,
                "stdout_omitted_chars": stdout_omitted,
                "stderr_omitted_chars": stderr_omitted,
                "captured_chars": len(combined_output),
            },
        )

    classification, warnings = _failure_classification(test_output)
    if classification == "environmental":
        warnings = (*warnings, "failure appears environmental")

    mode = EnvelopeMode.EXACT if omitted_count == 0 else EnvelopeMode.TRUNCATED
    summary = _failure_summary(test_output, classification=classification)
    return ResponseEnvelope(
        kind="test_output",
        mode=mode,
        summary=summary,
        items=tuple(items),
        omitted_count=omitted_count,
        original_result_id=result_id,
        retrieval_available=False,
        retrieval_hints=(),
        confidence=_confidence_for(test_output, omitted_count=omitted_count),
        warnings=warnings + _replacement_warnings(test_output),
        stats={
            "failed_test_count": len(test_output.failed_test_names),
            "relevant_file_count": len(test_output.relevant_files),
            "stdout_chars": len(test_output.stdout),
            "stderr_chars": len(test_output.stderr),
            "captured_chars": len(combined_output),
            "omitted_chars": omitted_count,
            "token_estimate": token_estimate,
            "traceback_frame_count": len(traceback_frames),
        },
    )


def _empty_or_pass_envelope(
    test_output: TestOutputRecord,
    *,
    result_id: str | None,
) -> ResponseEnvelope:
    combined_output = test_output.stdout + test_output.stderr
    if combined_output == "":
        return ResponseEnvelope(
            kind="test_output",
            mode=EnvelopeMode.EXACT,
            summary="Test run completed with no output.",
            items=(),
            omitted_count=0,
            original_result_id=result_id,
            retrieval_available=False,
            retrieval_hints=(),
            confidence=EnvelopeConfidence.HIGH,
            warnings=_replacement_warnings(test_output),
            stats={
                "failed_test_count": 0,
                "relevant_file_count": len(test_output.relevant_files),
                "stdout_chars": 0,
                "stderr_chars": 0,
                "captured_chars": 0,
                "omitted_chars": 0,
                "token_estimate": 0,
                "traceback_frame_count": 0,
            },
        )

    stdout_preview, stdout_omitted = _preview_text(test_output.stdout)
    stderr_preview, stderr_omitted = _preview_text(test_output.stderr)
    omitted_count = stdout_omitted + stderr_omitted
    original_result_id = result_id or test_output.name
    return ResponseEnvelope(
        kind="test_output",
        mode=EnvelopeMode.SUMMARIZED,
        summary=(
            f"Passing test output summarized for {original_result_id}; "
            f"{omitted_count} characters omitted."
        ),
        items=(
            {
                "type": "passing_output_summary",
                "stdout_preview": stdout_preview,
                "stderr_preview": stderr_preview,
                "stdout_omitted_chars": stdout_omitted,
                "stderr_omitted_chars": stderr_omitted,
                "captured_chars": len(combined_output),
            },
        ),
        omitted_count=omitted_count,
        original_result_id=original_result_id,
        retrieval_available=True,
        retrieval_hints=(f"retrieve_result(result_id='{original_result_id}')",),
        confidence=EnvelopeConfidence.MEDIUM,
        warnings=(
            "passing output summarized for retrieval",
            *_replacement_warnings(test_output),
        ),
        stats={
            "failed_test_count": 0,
            "relevant_file_count": len(test_output.relevant_files),
            "stdout_chars": len(test_output.stdout),
            "stderr_chars": len(test_output.stderr),
            "captured_chars": len(combined_output),
            "omitted_chars": omitted_count,
            "token_estimate": estimate_token_usage(combined_output).tokens,
            "traceback_frame_count": 0,
        },
    )


def _failure_summary(
    test_output: TestOutputRecord,
    *,
    classification: str,
) -> str:
    failed_count = len(test_output.failed_test_names)
    first_test = test_output.failed_test_names[0] if failed_count else test_output.name
    if classification == "environmental":
        return (
            f"{failed_count or 1} failing test(s) in {first_test}; "
            "likely environmental."
        )
    if test_output.assertion_summary is not None:
        return (
            f"{failed_count or 1} failing test(s) in {first_test}: "
            f"{test_output.assertion_summary}."
        )
    if test_output.traceback_root_cause is not None:
        return (
            f"{failed_count or 1} failing test(s) in {first_test}: "
            f"{test_output.traceback_root_cause}."
        )
    return f"{failed_count or 1} failing test(s) in {first_test}."


def _failure_classification(
    test_output: TestOutputRecord,
) -> tuple[str, tuple[str, ...]]:
    if test_output.deterministic is True:
        return "deterministic", ()
    if test_output.deterministic is False:
        return "environmental", ("classified from fixture metadata",)
    return "unknown", ("deterministic classification unavailable",)


def _confidence_for(
    test_output: TestOutputRecord,
    *,
    omitted_count: int,
) -> EnvelopeConfidence:
    if test_output.deterministic is None:
        return EnvelopeConfidence.LOW
    if omitted_count > 0:
        return EnvelopeConfidence.MEDIUM
    return EnvelopeConfidence.HIGH


def _classification_label(test_output: TestOutputRecord) -> str:
    if test_output.deterministic is True:
        return "deterministic"
    if test_output.deterministic is False:
        return "environmental"
    return "unknown"


def _replacement_warnings(test_output: TestOutputRecord) -> tuple[str, ...]:
    warnings: list[str] = []
    if "\ufffd" in test_output.stdout or "\ufffd" in test_output.stderr:
        warnings.append("decoded text contains replacement characters")
    return tuple(warnings)


def _preview_text(text: str) -> tuple[str, int]:
    if len(text) <= _MAX_PREVIEW_CHARS:
        return text, 0
    return text[:_MAX_PREVIEW_CHARS], len(text) - _MAX_PREVIEW_CHARS


def _extract_traceback_frames(stderr: str) -> tuple[dict[str, str | int], ...]:
    frames: list[dict[str, str | int]] = []
    for line in stderr.splitlines():
        match = _TRACEBACK_FRAME_RE.match(line)
        if match is None:
            continue
        frames.append(
            {
                "file": match.group("file"),
                "line": int(match.group("line")),
                "function": match.group("function"),
            },
        )
    return tuple(frames)
