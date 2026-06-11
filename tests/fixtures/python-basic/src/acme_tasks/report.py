from __future__ import annotations


def render_priority_report(user: str, task_count: int) -> str:
    status = "pending-review"
    return f"{user}: {task_count} tasks require {status}"
