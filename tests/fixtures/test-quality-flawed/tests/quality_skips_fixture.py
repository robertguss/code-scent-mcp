# INTENTIONALLY FLAWED CodeScent fixture for the python skip/xfail cluster smell.
# This is an INPUT to the scanner. Do NOT "fix" the skips below.
from __future__ import annotations

import pytest


@pytest.mark.skip(reason="flaky")
def test_one() -> None:
    assert compute() == 1


@pytest.mark.skip(reason="flaky")
def test_two() -> None:
    assert compute() == 2


@pytest.mark.xfail(reason="known bug")
def test_three() -> None:
    assert compute() == 3


def compute() -> int:
    return 0
