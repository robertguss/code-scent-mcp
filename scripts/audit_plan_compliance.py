#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "typer>=0.12",
# ]
# ///

# ─── How to run ───
#   uv run python scripts/audit_plan_compliance.py \
#     --plan .omo/plans/codescent-python-mvp.md --evidence .omo/evidence
# ──────────────────

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Final

import typer

from codescent.core.public_surface import (
    LOCKED_POST_MVP_MCP_TOOL_NAMES,
    POST_MVP_CLI_COMMAND_NAMES,
    PUBLIC_SURFACE,
    REGISTERED_MCP_TOOL_NAMES,
    SurfaceStage,
    registered_mcp_tool_names,
)

type JsonValue = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

if TYPE_CHECKING:
    from collections.abc import Iterable

DECISION_PHRASES: Final[tuple[str, ...]] = (
    "python-first mvp",
    "writes only .codescent",
    "does not edit analyzed source files",
    "local stdio",
    "deterministic offline eval",
    "agent-in-the-loop eval",
    "lx_data_lake",
)
DOC_PATHS: Final[tuple[Path, ...]] = (
    Path("README.md"),
    Path("docs/evals.md"),
    Path("docs/mcp-tools.md"),
)


@dataclass(frozen=True, slots=True)
class AuditResult:
    ok: bool
    unchecked_todos: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    tool_surface_ok: bool
    user_decisions_ok: bool
    details: dict[str, JsonValue]


def audit(plan: Path, evidence: Path) -> AuditResult:
    plan_text = plan.read_text()
    unchecked_todos = tuple(_unchecked_todos(plan_text))
    expected_evidence = _expected_evidence_prefixes(plan, plan_text)
    missing_evidence = tuple(
        prefix for prefix in expected_evidence if not list(evidence.glob(f"{prefix}*"))
    )
    tool_surface = _tool_surface()
    decisions = _decision_phrases()
    completion_ready = not unchecked_todos
    ok = not missing_evidence and tool_surface["ok"] is True and decisions["ok"] is True
    ok = ok and completion_ready
    return AuditResult(
        ok=ok,
        unchecked_todos=unchecked_todos,
        missing_evidence=missing_evidence,
        tool_surface_ok=tool_surface["ok"] is True,
        user_decisions_ok=decisions["ok"] is True,
        details={
            "tool_surface": tool_surface,
            "user_decisions": decisions,
        },
    )


def _unchecked_todos(plan_text: str) -> list[str]:
    return [
        line.strip()
        for line in plan_text.splitlines()
        if re.match(r"^- \[ \] (?:[1-9]|[1-2][0-9]|3[0-2]|F[1-5])\.", line)
    ]


def _checked_todo_numbers(plan_text: str) -> tuple[int, ...]:
    numbers: list[int] = []
    for line in plan_text.splitlines():
        match = re.match(r"^- \[x\] ([1-9]|[1-2][0-9]|3[0-2])\.", line)
        if match is not None:
            numbers.append(int(match.group(1)))
    return tuple(numbers)


def _expected_evidence_prefixes(plan: Path, plan_text: str) -> tuple[str, ...]:
    if plan.name == "codescent-prd-remainder.md":
        task_prefixes = tuple(
            f"prd-remainder-task-{number}-"
            for number in _checked_todo_numbers(plan_text)
        )
        final_prefixes = tuple(
            prefix
            for checkbox, prefix in (
                ("F1.", "prd-remainder-final-plan-compliance"),
                ("F2.", "prd-remainder-final-code-quality"),
                ("F3.", "prd-remainder-final-smoke"),
                ("F4.", "prd-remainder-final-runtime-safety"),
                ("F5.", "prd-remainder-final-dashboard"),
            )
            if f"- [x] {checkbox}" in plan_text
        )
        return task_prefixes + final_prefixes
    return tuple(f"task-{index}-" for index in range(1, 21))


def _tool_surface() -> dict[str, JsonValue]:
    registered_tools = registered_mcp_tool_names()
    post_mvp_tools = frozenset(
        entry.name for entry in PUBLIC_SURFACE.mcp_tools if not entry.registered
    )
    post_mvp_commands = frozenset(
        entry.name
        for entry in PUBLIC_SURFACE.cli_commands
        if entry.stage is SurfaceStage.POST_MVP
    )
    return {
        "ok": (
            registered_tools == REGISTERED_MCP_TOOL_NAMES
            and post_mvp_tools >= LOCKED_POST_MVP_MCP_TOOL_NAMES
            and post_mvp_commands >= POST_MVP_CLI_COMMAND_NAMES
        ),
        "tool_count": len(registered_tools),
        "missing": _json_string_list(
            sorted(REGISTERED_MCP_TOOL_NAMES - registered_tools),
        ),
        "unexpected": _json_string_list(
            sorted(registered_tools - REGISTERED_MCP_TOOL_NAMES),
        ),
        "post_mvp_declared": _json_string_list(sorted(post_mvp_tools)),
        "post_mvp_cli_declared": _json_string_list(sorted(post_mvp_commands)),
    }


def _decision_phrases() -> dict[str, JsonValue]:
    combined = "\n".join(path.read_text().lower() for path in DOC_PATHS)
    missing = [phrase for phrase in DECISION_PHRASES if phrase not in combined]
    return {"ok": not missing, "missing": _json_string_list(missing)}


def _json_string_list(values: Iterable[JsonValue]) -> list[JsonValue]:
    return list(values)


def _write_json(path: Path, payload: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _audit_output_name(plan: Path) -> str:
    if plan.name == "codescent-prd-remainder.md":
        return "prd-remainder-plan-compliance.json"
    return "final-plan-compliance.json"


def main(
    plan: Annotated[Path, typer.Option()],
    evidence: Annotated[Path, typer.Option()],
) -> None:
    result = audit(plan, evidence)
    payload: dict[str, JsonValue] = {
        "ok": result.ok,
        "unchecked_todos": list(result.unchecked_todos),
        "missing_evidence": list(result.missing_evidence),
        "tool_surface_ok": result.tool_surface_ok,
        "user_decisions_ok": result.user_decisions_ok,
        "details": result.details,
    }
    out = evidence / _audit_output_name(plan)
    _write_json(out, payload)
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    if not result.ok:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)
