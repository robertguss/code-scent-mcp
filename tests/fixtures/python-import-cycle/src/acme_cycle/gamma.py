from __future__ import annotations

from acme_cycle.alpha import alpha_value


def gamma_value() -> str:
    return f"gamma::{alpha_value()}"
