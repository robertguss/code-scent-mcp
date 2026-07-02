from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codescent.engine.inventory import build_file_inventory
from codescent.mcp.context_tools import (
    find_symbol,
    get_file_context,
    get_symbol_context,
)
from codescent.mcp.finding_tools import (
    list_findings,
    rescan,
    scan_code_health,
)
from codescent.mcp.planning_tools import (
    get_finding_context,
    plan_refactor,
    suggest_tests,
)
from codescent.mcp.repo_tools import get_repo_map, get_repo_status
from codescent.mcp.search_tools import search_content, search_files
from codescent.services.symbols import SymbolService
from codescent.smoke.lx_data_lake_contract import (
    LX_REQUIRED_EXCLUDES,
    JsonValue,
    build_smoke_plan,
)

__all__ = ["LX_REQUIRED_EXCLUDES", "build_smoke_plan"]

GIT_STATUS_TIMEOUT_SECONDS = 5


def run_smoke(repo: Path, out: Path, *, dry_run: bool) -> dict[str, JsonValue]:
    plan = build_smoke_plan(repo)
    if dry_run:
        payload: dict[str, JsonValue] = {
            "ok": True,
            "dry_run": True,
            "repo": _display_repo(plan.repo),
            "excluded_paths": list(plan.excluded_paths),
            "tool_calls": list(plan.tool_calls),
        }
        _write_json(out, payload)
        return payload

    shutil.rmtree(repo / ".codescent", ignore_errors=True)
    start = time.perf_counter()
    status_before = _git_status_without_codescent(repo)
    before = _source_hashes(repo)
    calls = _execute_tool_loop(repo)
    after = _source_hashes(repo)
    status_after = _git_status_without_codescent(repo)
    inventory_paths = tuple(item.path for item in build_file_inventory(repo))
    excluded_absence = _excluded_absence(inventory_paths, plan.excluded_paths)
    changed_paths = sorted(
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    )
    source_hashes_unchanged = before == after
    git_status_unchanged = status_before == status_after
    payload: dict[str, JsonValue] = {
        "ok": (
            source_hashes_unchanged
            and not changed_paths
            and git_status_unchanged
            and all(excluded_absence.values())
        ),
        "repo": _display_repo(repo),
        "dry_run": False,
        "excluded_paths": list(plan.excluded_paths),
        "excluded_paths_absent_from_inventory": excluded_absence,
        "tool_calls": calls,
        "findings": _finding_summary(calls),
        "telemetry": {"elapsed_ms": int((time.perf_counter() - start) * 1000)},
        "source_hashes_unchanged": source_hashes_unchanged,
        "changed_paths": changed_paths,
        "git_status_unchanged_except_codescent": git_status_unchanged,
        "git_status_before": list(status_before),
        "git_status_after": list(status_after),
        "allowed_changed_root": ".codescent",
    }
    _write_json(out, payload)
    return payload


def _execute_tool_loop(repo: Path) -> list[dict[str, JsonValue]]:
    repo_text = repo.as_posix()
    calls: list[dict[str, JsonValue]] = []
    repo_map = _record(calls, "get_repo_map", get_repo_map(repo_text))
    _record(calls, "get_repo_status", get_repo_status(repo_text))
    _record(calls, "search_files", search_files("cli", repo=repo_text))
    _record(calls, "search_content", search_content("Typer", repo=repo_text))
    symbols = _record(calls, "find_symbol", find_symbol("app", repo=repo_text))
    context_path = _context_path(repo_map)
    _record(calls, "get_file_context", get_file_context(context_path, repo=repo_text))
    qualified_name = _qualified_symbol(symbols)
    if qualified_name is not None:
        _record(
            calls,
            "get_symbol_context",
            get_symbol_context(qualified_name, repo=repo_text),
        )
    _record(calls, "scan_code_health", scan_code_health(repo_text))
    report = _record(calls, "list_findings", list_findings(repo_text))
    context_paths = frozenset(file.path for file in SymbolService(repo).extract().files)
    finding_id = _finding_id_from_report(report, context_paths)
    if finding_id is not None:
        _record(
            calls,
            "get_finding_context",
            get_finding_context(finding_id, repo=repo_text),
        )
        _record(calls, "plan_refactor", plan_refactor(finding_id, repo=repo_text))
        _record(calls, "suggest_tests", suggest_tests(finding_id, repo=repo_text))
    _record(calls, "rescan", rescan(repo_text))
    return calls


def _record(
    calls: list[dict[str, JsonValue]],
    tool: str,
    data: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    calls.append({"tool": tool, "data": _jsonable(data)})
    return data


def _source_hashes(repo: Path) -> dict[str, str]:
    return {
        item.path: hashlib.sha256((repo / item.path).read_bytes()).hexdigest()
        for item in build_file_inventory(repo)
    }


def _excluded_absence(
    inventory_paths: tuple[str, ...],
    excluded_paths: tuple[str, ...],
) -> dict[str, bool]:
    return {
        excluded: all(excluded not in Path(path).parts for path in inventory_paths)
        for excluded in excluded_paths
    }


def _git_status_without_codescent(repo: Path) -> tuple[str, ...]:
    git_path = shutil.which("git")
    if git_path is None:
        return ()
    completed = subprocess.run(  # nosec B603 - resolved git path, shell=False.
        [git_path, "status", "--short", "--untracked-files=all"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_STATUS_TIMEOUT_SECONDS,
    )
    return tuple(
        line for line in completed.stdout.splitlines() if ".codescent/" not in line
    )


def _finding_summary(calls: list[dict[str, JsonValue]]) -> dict[str, JsonValue]:
    scan = _call_data(calls, "scan_code_health")
    report = _call_data(calls, "list_findings")
    return {
        "created": scan.get("findings_created", 0),
        "rule_ids": scan.get("rule_ids", []),
        "open_count": report.get("open_count", 0),
    }


def _call_data(calls: list[dict[str, JsonValue]], tool: str) -> dict[str, JsonValue]:
    for call in calls:
        if call["tool"] != tool:
            continue
        data = call["data"]
        if isinstance(data, dict):
            return data
    return {}


def _context_path(repo_map: dict[str, JsonValue]) -> str:
    entrypoints = repo_map.get("entrypoints")
    if isinstance(entrypoints, tuple) and entrypoints:
        return _first_string(entrypoints) or "src/lx_data_lake/cli.py"
    sample_files = repo_map.get("sample_files")
    if isinstance(sample_files, tuple) and sample_files:
        return _first_string(sample_files) or "src/lx_data_lake/cli.py"
    return "src/lx_data_lake/cli.py"


def _qualified_symbol(symbols: dict[str, JsonValue]) -> str | None:
    results = symbols.get("results")
    if not isinstance(results, tuple) or not results:
        return None
    first = results[0]
    if not isinstance(first, dict):
        return None
    qualified_name = first.get("qualified_name")
    return (
        qualified_name if isinstance(qualified_name, str) and qualified_name else None
    )


def _first_string(values: tuple[JsonValue, ...]) -> str | None:
    return next((value for value in values if isinstance(value, str)), None)


def _finding_id_from_report(
    report: dict[str, JsonValue],
    context_paths: frozenset[str],
) -> str | None:
    findings = report.get("findings")
    if not isinstance(findings, tuple):
        return None
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        file_path = finding.get("file_path")
        finding_id = finding.get("finding_id")
        if (
            isinstance(file_path, str)
            and file_path in context_paths
            and isinstance(finding_id, str)
            and finding_id
        ):
            return finding_id
    return None


def _jsonable(value: JsonValue) -> JsonValue:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _write_json(out: Path, payload: dict[str, JsonValue]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    _ = out.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _display_repo(repo: Path) -> str:
    try:
        return repo.resolve().relative_to(Path.cwd()).as_posix()
    except ValueError:
        return repo.name


def main(
    repo: Annotated[Path, typer.Option()],
    out: Annotated[Path, typer.Option()],
    dry_run: Annotated[bool, typer.Option()] = False,
) -> None:
    payload = run_smoke(repo, out, dry_run=dry_run)
    typer.echo(json.dumps({"ok": payload["ok"], "dry_run": payload["dry_run"]}))


if __name__ == "__main__":
    typer.run(main)
