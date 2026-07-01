"""CLI + gate for the agent-experience eval suite (plan units U1/U8).

Examples:
    # Print the current agent-experience report as JSON
    uv run python evals/run_agent_ux.py

    # Re-record the committed baseline after a reviewed change
    uv run python evals/run_agent_ux.py --update-baseline

    # CI gate: fail (exit 1) if a gated dimension regressed below the baseline
    uv run python evals/run_agent_ux.py --check

The offline ``--check`` is the phase-two per-cluster gate: deterministic
dimensions (R2-R5) plus token cost (R6). R1 tool-selection is scored with the
offline heuristic proxy and reported for visibility, but is advisory -- the gate
never fails on it (see ``agent_ux.gate``). The authoritative R1 score comes from
a live model at milestones, wired by the owner behind the ``live_model`` marker.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Annotated

import typer

# R2/R4 deliberately call tools with malformed args to prove they return
# recoverable error envelopes; FastMCP logs each caught error at ERROR level.
# Disable globally (survives FastMCP re-configuring its own logger) so the
# eval's own JSON is the only output.
logging.disable(logging.ERROR)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codescent.evals.agent_ux import AgentUxReport, build_agent_ux_report  # noqa: E402
from codescent.evals.agent_ux.gate import find_regressions  # noqa: E402
from codescent.evals.agent_ux.tool_selection import load_selection_tasks  # noqa: E402

DEFAULT_BASELINES_PATH = Path(__file__).resolve().parent / "agent_ux_baselines.json"
DEFAULT_TASKS_PATH = Path(__file__).resolve().parent / "tool_selection_tasks.json"


def main(
    *,
    baselines: Annotated[Path, typer.Option()] = DEFAULT_BASELINES_PATH,
    tasks_path: Annotated[Path, typer.Option()] = DEFAULT_TASKS_PATH,
    check: Annotated[
        bool, typer.Option(help="Fail when a gated dimension regresses below baseline.")
    ] = False,
    update_baseline: Annotated[
        bool, typer.Option(help="Rewrite the baselines file from the current run.")
    ] = False,
) -> None:
    tasks = load_selection_tasks(tasks_path)
    report = asyncio.run(build_agent_ux_report(tasks=tasks))

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
        regressions = find_regressions(report, recorded)
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
