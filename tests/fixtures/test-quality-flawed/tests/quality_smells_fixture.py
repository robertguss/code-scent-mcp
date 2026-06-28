# INTENTIONALLY FLAWED CodeScent fixture for python test-quality smells.
# This is an INPUT to the scanner. Do NOT "fix" the smells below.
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_assertion_free() -> None:
    result = 1 + 1
    print(result)


def test_always_passes() -> None:
    assert True


def test_pass_only_body() -> None:
    pass


@patch("os.getcwd")
def test_over_mocked(mock_cwd: MagicMock) -> None:
    first = MagicMock()
    second = MagicMock()
    third = MagicMock()
    first.run()
    second.run()
    third.run()
    mock_cwd.return_value = "/tmp"
