# Healthy CodeScent fixture: well-formed python tests that must produce ZERO
# test-quality findings (the no-false-positive acceptance bar).
from __future__ import annotations

from unittest.mock import MagicMock


def add(left: int, right: int) -> int:
    return left + right


def test_addition_returns_sum() -> None:
    assert add(1, 2) == 3


def test_uses_one_mock_with_real_assertion() -> None:
    service = MagicMock()
    service.fetch.return_value = 42
    result = service.fetch()
    assert result == 42
