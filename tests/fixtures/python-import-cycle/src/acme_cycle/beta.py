from __future__ import annotations

from acme_cycle.gamma import gamma_value


def beta_value() -> str:
    return f"beta::{gamma_value()}"
