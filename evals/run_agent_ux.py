"""CLI + gate for the agent-experience eval suite (plan units U1/U8).

Examples:
    # Print the current agent-experience report as JSON
    uv run python evals/run_agent_ux.py

    # Re-record the committed baseline after a reviewed change
    uv run python evals/run_agent_ux.py --update-baseline

    # CI gate: fail (exit 1) if a dimension regressed below the baseline
    uv run python evals/run_agent_ux.py --check

The offline ``--check`` is the phase-two per-cluster gate: deterministic
dimensions (R2-R5) plus token cost (R6). The model-driven R1 dimension is scored
only with ``--live-model`` at milestones (added by U7/U8) and is never part of
the default gate.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codescent.evals.agent_ux import AgentUxReport, build_agent_ux_report

DEFAULT_BASELINES_PATH = Path(__file__).resolve().parent / "agent_ux_baselines.json"
_REGRESSION_TOLERANCE = 1e-9
_NO_INCREASE_UNITS = frozenset({"tokens"})


def _regressions(
    current: AgentUxReport,
    baseline: AgentUxReport,
) -> list[dict[str, object]]:
    """Compare a fresh run against the baseline and list any regressions.

    Share/accuracy dimensions regress when they drop below baseline; token-cost
    dimensions regress when they rise above it; a baselined dimension missing
    from the current run is a full regression (mirrors ``check_regression``).
    """
    out: list[dict[str, object]] = []
    for base_dim in baseline.dimensions:
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


def main(
    *,
    baselines: Annotated[Path, typer.Option()] = DEFAULT_BASELINES_PATH,
    check: Annotated[
        bool, typer.Option(help="Fail when a dimension regresses below baseline.")
    ] = False,
    update_baseline: Annotated[
        bool, typer.Option(help="Rewrite the baselines file from the current run.")
    ] = False,
) -> None:
    report = asyncio.run(build_agent_ux_report())

    if update_baseline:
        _ = baselines.write_text(report.model_dump_json(indent=2) + "\n")
        typer.echo(
            json.dumps(
                {
                    "updated_baselines": baselines.as_posix(),
                    "dimensions": len(report.dimensions),
                }
            )
        )
        return

    if check:
        recorded = AgentUxReport.model_validate_json(baselines.read_text())
        regressions = _regressions(report, recorded)
        typer.echo(
            json.dumps(
                {
                    "passed": not regressions,
                    "dimensions": len(report.dimensions),
                    "regressions": regressions,
                }
            )
        )
        if regressions:
            raise typer.Exit(code=1)
        return

    typer.echo(report.model_dump_json(indent=2))


if __name__ == "__main__":
    typer.run(main)
