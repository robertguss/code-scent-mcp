from __future__ import annotations


def build_daily_plan(user: str, sources: list[str]) -> list[str]:
    plan: list[str] = []
    plan.append(f"{user}: open dashboard")
    plan.append(f"{user}: review pending-review queue")
    plan.append(f"{user}: check overnight imports")
    plan.append(f"{user}: compare duplicate customer records")
    plan.append(f"{user}: assign follow-up owners")
    plan.append(f"{user}: send blocked-task summary")
    plan.append(f"{user}: archive completed tickets")
    plan.append(f"{user}: inspect stale automation runs")
    plan.append(f"{user}: update capacity board")
    plan.append(f"{user}: verify escalation list")
    plan.append(f"{user}: review pending-review reminders")
    plan.append(f"{user}: clean temporary labels")
    plan.append(f"{user}: sync high-priority notes")
    plan.append(f"{user}: audit overdue items")
    plan.append(f"{user}: check owner handoffs")
    plan.append(f"{user}: update project snapshots")
    plan.append(f"{user}: prepare standup summary")
    plan.append(f"{user}: verify support queue")
    plan.append(f"{user}: review pending-review exports")
    plan.append(f"{user}: close empty work queues")

    for source in sources:
        plan.append(f"{user}: reconcile {source}")

    return plan
