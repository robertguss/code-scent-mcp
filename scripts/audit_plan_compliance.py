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
from typing import Annotated, Final

import typer

type JsonValue = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

MVP_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "get_repo_map",
        "get_repo_status",
        "search_files",
        "search_content",
        "find_symbol",
        "get_file_context",
        "get_symbol_context",
        "scan_code_health",
        "get_smell_report",
        "get_finding_context",
        "get_next_improvement",
        "plan_refactor",
        "suggest_tests",
        "mark_finding",
        "rescan",
    },
)
POST_MVP_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "find_references",
        "get_impact",
        "verify_change",
        "report",
        "reset",
    },
)
DECISION_PHRASES: Final[tuple[str, ...]] = (
    "python-first mvp",
    "writes only .codescent",
    "does not edit analyzed source files",
    "local stdio",
    "deterministic offline eval",
    "agent-in-the-loop eval",
    "/users/robertguss/projects/wts-lx/lx_data_lake",
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
    expected_evidence = tuple(f"task-{index}-" for index in range(1, 21))
    missing_evidence = tuple(
        prefix for prefix in expected_evidence if not list(evidence.glob(f"{prefix}*"))
    )
    tool_surface = _tool_surface()
    decisions = _decision_phrases()
    ok = (
        not unchecked_todos
        and not missing_evidence
        and tool_surface["ok"] is True
        and decisions["ok"] is True
    )
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
        if re.match(r"^- \[ \] (?:[1-9]|1[0-9]|20)\.", line)
    ]


def _tool_surface() -> dict[str, JsonValue]:
    text = Path("docs/mcp-tools.md").read_text()
    tools = {
        line.removeprefix("- `").removesuffix("`")
        for line in text.splitlines()
        if line.startswith("- `")
    }
    return {
        "ok": tools == MVP_TOOLS and not tools.intersection(POST_MVP_TOOLS),
        "tool_count": len(tools),
        "missing": sorted(MVP_TOOLS - tools),
        "unexpected": sorted(tools - MVP_TOOLS),
        "post_mvp_exposed": sorted(tools.intersection(POST_MVP_TOOLS)),
    }


def _decision_phrases() -> dict[str, JsonValue]:
    combined = "\n".join(path.read_text().lower() for path in DOC_PATHS)
    missing = [phrase for phrase in DECISION_PHRASES if phrase not in combined]
    return {"ok": not missing, "missing": missing}


def _write_json(path: Path, payload: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload, indent=2, sort_keys=True))


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
    out = evidence / "final-plan-compliance.json"
    _write_json(out, payload)
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    if not result.ok:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)
