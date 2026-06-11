from __future__ import annotations

from acme_tasks.workflow import build_daily_plan


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: acme-tasks USER")
        return 2

    plan = build_daily_plan(argv[0], ["inbox", "calendar", "review"])
    print("\n".join(plan))
    return 0
