from __future__ import annotations

from codescent.core.errors import CodeScentError, ErrorCode, ErrorSeverity


def test_error_payload_is_structured() -> None:
    error = CodeScentError(
        code=ErrorCode.INVALID_REPO_ROOT,
        message="Repository root does not exist.",
        severity=ErrorSeverity.ERROR,
        details={"repo": "/missing"},
    )

    assert error.to_payload() == {
        "code": "invalid_repo_root",
        "message": "Repository root does not exist.",
        "severity": "error",
        "details": {"repo": "/missing"},
    }


def test_error_string_contains_code_and_message() -> None:
    error = CodeScentError(
        code=ErrorCode.STALE_INDEX,
        message="Index is stale.",
        severity=ErrorSeverity.WARNING,
    )

    assert str(error) == "stale_index: Index is stale."
