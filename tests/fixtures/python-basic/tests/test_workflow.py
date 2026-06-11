from __future__ import annotations

from acme_tasks.workflow import build_daily_plan


def test_build_daily_plan_includes_sources() -> None:
    plan = build_daily_plan("ana", ["inbox"])

    assert "ana: reconcile inbox" in plan
