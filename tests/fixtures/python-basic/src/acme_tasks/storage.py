from __future__ import annotations


def save_plan(user: str, plan: list[str]) -> dict[str, object]:
    return {"user": user, "saved": True, "items": list(plan)}
