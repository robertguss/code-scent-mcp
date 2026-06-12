from __future__ import annotations

import hashlib
import json
import shutil
import socket
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codescent.engine.inventory import build_file_inventory
from codescent.mcp.finding_tools import (
    get_smell_report,
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

if TYPE_CHECKING:
    from codescent.smoke.lx_data_lake_contract import JsonValue


def prove_source_read_only(repo: Path, out: Path) -> dict[str, JsonValue]:
    shutil.rmtree(repo / ".codescent", ignore_errors=True)
    before = _source_hashes(repo)
    attempts: list[str] = []
    original_socket = socket.socket
    socket.socket = _blocked_socket(attempts)
    try:
        calls = _tool_calls(repo)
    finally:
        socket.socket = original_socket
    after = _source_hashes(repo)
    changed_paths = _changed_paths(before, after)
    source_hashes_unchanged = before == after
    network_attempts = len(attempts)
    payload: dict[str, JsonValue] = {
        "ok": source_hashes_unchanged and not changed_paths and network_attempts == 0,
        "repo": _display_repo(repo),
        "allowed_changed_root": ".codescent",
        "source_hashes_unchanged": source_hashes_unchanged,
        "changed_paths": changed_paths,
        "network_attempts": network_attempts,
        "tool_calls": calls,
    }
    _write_json(out, payload)
    return payload


def _blocked_socket(
    attempts: list[str],
) -> type[socket.socket]:
    class BlockedSocket(socket.socket):
        def __new__(
            cls,
            *args: JsonValue,
            **kwargs: JsonValue,
        ) -> socket.socket:
            _ = cls, args, kwargs
            attempts.append("socket")
            message = "network disabled"
            raise AssertionError(message)

    return BlockedSocket


def _tool_calls(repo: Path) -> list[dict[str, JsonValue]]:
    repo_text = repo.as_posix()
    calls: list[dict[str, JsonValue]] = []
    _record(calls, "get_repo_map", get_repo_map(repo_text))
    _record(calls, "get_repo_status", get_repo_status(repo_text))
    _record(calls, "search_files", search_files("workflow", repo=repo_text))
    _record(calls, "search_content", search_content("pending-review", repo=repo_text))
    scan = _record(calls, "scan_code_health", scan_code_health(repo_text))
    _record(calls, "get_smell_report", get_smell_report(repo_text))
    finding_id = _first_finding_id(scan)
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


def _changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    )


def _first_finding_id(scan: dict[str, JsonValue]) -> str | None:
    finding_ids = scan.get("finding_ids")
    if not isinstance(finding_ids, tuple) or not finding_ids:
        return None
    first = finding_ids[0]
    return first if isinstance(first, str) else None


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
) -> None:
    payload = prove_source_read_only(repo, out)
    typer.echo(json.dumps({"ok": payload["ok"]}))


if __name__ == "__main__":
    typer.run(main)
