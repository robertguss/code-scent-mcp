"""Regression gate for the agent-experience baseline (plan U8, R7).

The gate is the phase-two per-cluster guard: deterministic dimensions (R2-R5)
plus token cost (R6). R1 tool-selection is an ``accuracy``-unit *advisory* signal
-- reported and baselined for visibility, but never gated, because the offline
heuristic proxy is non-authoritative and the live-model score is a milestone
aggregate, not a per-merge gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codescent.evals.agent_ux.models import AgentUxReport

_REGRESSION_TOLERANCE = 1e-9
_NO_INCREASE_UNITS = frozenset({"tokens"})
_ADVISORY_UNITS = frozenset({"accuracy"})


def find_regressions(
    current: AgentUxReport,
    baseline: AgentUxReport,
) -> list[dict[str, object]]:
    """Compare a fresh run against the baseline and list any regressions.

    Share dimensions regress when they drop below baseline; token-cost
    dimensions regress when they rise above it; a baselined dimension missing
    from the current run is a full regression. ``accuracy``-unit dimensions (R1)
    are advisory and never counted.
    """
    out: list[dict[str, object]] = []
    for base_dim in baseline.dimensions:
        if base_dim.unit in _ADVISORY_UNITS:
            continue
        measured = current.dimension(base_dim.name)
        if measured is None:
            out.append(
                {
                    "name": base_dim.name,
                    "baseline": base_dim.value,
                    "reason": "vanished",
                }
            )
            continue
        if base_dim.unit in _NO_INCREASE_UNITS:
            if measured.value > base_dim.value + _REGRESSION_TOLERANCE:
                out.append(
                    {
                        "name": base_dim.name,
                        "baseline": base_dim.value,
                        "measured": measured.value,
                        "reason": "increased",
                    }
                )
        elif measured.value < base_dim.value - _REGRESSION_TOLERANCE:
            out.append(
                {
                    "name": base_dim.name,
                    "baseline": base_dim.value,
                    "measured": measured.value,
                    "reason": "regressed",
                }
            )
    return out
