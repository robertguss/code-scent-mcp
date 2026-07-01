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
    from codescent.evals.agent_ux.models import AgentUxReport, DimensionResult

_REGRESSION_TOLERANCE = 1e-9
_NO_INCREASE_UNITS = frozenset({"tokens"})
_ADVISORY_UNITS = frozenset({"accuracy"})
# Every unit a scorer emits. A typo'd unit (e.g. "token") would silently fall to
# the wrong gate branch, so an unknown unit is a hard error, not a skip.
_KNOWN_UNITS = frozenset({"share", "tokens", "accuracy"})


def _regression_for(
    base_dim: DimensionResult,
    measured: DimensionResult | None,
) -> dict[str, object] | None:
    """The regression entry for one baselined dimension, or None if it held.

    A missing dimension is ``vanished`` for every unit (including advisory
    ``accuracy``), so a silently dropped dimension can never read as a pass. A
    *present* advisory dimension's value drift never gates. Token-cost regresses
    on increase; share on decrease.
    """
    if measured is None:
        return {"name": base_dim.name, "baseline": base_dim.value, "reason": "vanished"}
    if base_dim.unit in _ADVISORY_UNITS:
        return None
    if base_dim.unit in _NO_INCREASE_UNITS:
        if measured.value > base_dim.value + _REGRESSION_TOLERANCE:
            return _entry(base_dim, measured, "increased")
        return None
    if measured.value < base_dim.value - _REGRESSION_TOLERANCE:
        return _entry(base_dim, measured, "regressed")
    return None


def _entry(
    base_dim: DimensionResult,
    measured: DimensionResult,
    reason: str,
) -> dict[str, object]:
    return {
        "name": base_dim.name,
        "baseline": base_dim.value,
        "measured": measured.value,
        "reason": reason,
    }


def find_regressions(
    current: AgentUxReport,
    baseline: AgentUxReport,
) -> list[dict[str, object]]:
    """List every gated regression of a fresh run against the baseline.

    Delegates the per-dimension decision to :func:`_regression_for`. An
    unrecognized unit raises rather than falling silently to the wrong branch.
    """
    out: list[dict[str, object]] = []
    for base_dim in baseline.dimensions:
        if base_dim.unit not in _KNOWN_UNITS:
            msg = f"dimension {base_dim.name!r} has unknown unit {base_dim.unit!r}"
            raise ValueError(msg)
        entry = _regression_for(base_dim, current.dimension(base_dim.name))
        if entry is not None:
            out.append(entry)
    return out
