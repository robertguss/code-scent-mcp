from __future__ import annotations

from codescent.core.errors import CodeScentError, ErrorCode, ErrorSeverity


def test_error_payload_is_structured() -> None:
    error = CodeScentError(
        code=ErrorCode.INVALID_REPO_ROOT,
        message="Repository root does not exist.",
        severity=ErrorSeverity.ERROR,
        details={"repo": "/missing"},
    )

    # Existing keys are preserved; the uniform envelope keys (ok/recoverable/data)
    # are added additively (U1).
    assert error.to_payload() == {
        "ok": False,
        "code": "invalid_repo_root",
        "message": "Repository root does not exist.",
        "severity": "error",
        "details": {"repo": "/missing"},
        "recoverable": True,
        "data": {"severity": "error", "details": {"repo": "/missing"}},
    }


def test_error_payload_surfaces_recovery_data() -> None:
    error = CodeScentError(
        code=ErrorCode.NOT_FOUND,
        message="No finding 'x'.",
        severity=ErrorSeverity.ERROR,
        recovery={"available_options": ["a", "b"], "fix_hint": "list them"},
    )

    payload = error.to_payload()
    assert payload["code"] == "not_found"
    assert payload["recoverable"] is True
    assert payload["data"]["available_options"] == ["a", "b"]
    assert payload["data"]["fix_hint"] == "list them"


def test_error_string_contains_code_and_message() -> None:
    error = CodeScentError(
        code=ErrorCode.STALE_INDEX,
        message="Index is stale.",
        severity=ErrorSeverity.WARNING,
    )

    assert str(error) == "stale_index: Index is stale."
