from __future__ import annotations

from acme_tasks.cli import main


def test_main_requires_user() -> None:
    assert main([]) == 2
