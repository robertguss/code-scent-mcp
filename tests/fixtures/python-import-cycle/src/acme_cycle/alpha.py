from __future__ import annotations

from acme_cycle.beta import beta_value


def alpha_value() -> str:
    return f"alpha::{beta_value()}"
