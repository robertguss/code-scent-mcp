from __future__ import annotations

from acme_tasks.config import load_config


def test_load_config_sets_environment() -> None:
    assert load_config("local")["environment"] == "local"
