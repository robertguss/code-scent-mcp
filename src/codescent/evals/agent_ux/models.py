"""Frozen result models for the agent-experience eval suite (plan unit U1).

The suite scores the MCP surface on six agent-experience dimensions (R1-R6).
Each dimension returns a :class:`DimensionResult`; a full run is an
:class:`AgentUxReport`. Models are frozen so they round-trip through the
committed ``evals/agent_ux_baselines.json`` unchanged, mirroring the existing
``TokenEfficiencyReport`` convention.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class ToolInfo(BaseModel):
    """One entry of the live ``tools/list`` manifest.

    ``input_schema_json`` is the JSON-serialized parameter schema so the model
    stays free of ``Any`` and the R6 token-cost dimension can count it directly.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    name: str
    description: str
    input_schema_json: str


class BreakdownEntry(BaseModel):
    """A single labelled sub-measurement (e.g. per-group token cost)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    label: str
    value: float


class DimensionResult(BaseModel):
    """The score for one agent-experience dimension.

    ``value`` is the gated number: a share in ``[0, 1]`` for the contract
    dimensions (R2-R5), an absolute token count for R6, an accuracy in
    ``[0, 1]`` for R1. ``unit`` names which and drives gate direction
    (``share``/``accuracy`` gate on no-regression, ``tokens`` on no-increase).
    ``passed``/``total`` back the share dimensions; ``notes`` explains any
    shortfall; ``breakdown`` carries optional per-item detail.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    name: str
    value: float
    unit: str
    passed: int = 0
    total: int = 0
    notes: tuple[str, ...] = ()
    breakdown: tuple[BreakdownEntry, ...] = ()


class AgentUxReport(BaseModel):
    """A full agent-experience run over one surface."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    repo: str
    surface_tool_count: int
    dimensions: tuple[DimensionResult, ...]

    def dimension(self, name: str) -> DimensionResult | None:
        """Return the dimension named ``name``, or ``None`` when absent."""
        return next((item for item in self.dimensions if item.name == name), None)
