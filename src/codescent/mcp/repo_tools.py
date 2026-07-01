from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypedDict

from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.services.bootstrap import (
    BootstrapNote,  # noqa: TC001  (runtime: fastmcp builds the TypedDict schema)
)
from codescent.services.config import ConfigService
from codescent.services.git import detect_git_state
from codescent.services.session_resume import RatchetStatus, SessionResumeService
from codescent.services.task_brief import TaskBriefService

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from codescent.services.session_resume import ResumeBrief
    from codescent.services.task_brief import TaskBrief

SAMPLE_FILE_LIMIT: Final = 20
CHANGED_FILE_LIMIT: Final = 20
ENTRYPOINT_NAMES: Final = frozenset({"__main__.py", "cli.py", "main.py"})


class RepoMapToolPayload(TypedDict):
    ok: bool
    read_only: bool
    file_count: int
    test_file_count: int
    languages: dict[str, int]
    top_level: tuple[str, ...]
    entrypoints: tuple[str, ...]
    sample_files: tuple[str, ...]


class RepoStatusToolPayload(TypedDict):
    ok: bool
    read_only: bool
    index_fresh: bool
    indexed_files: int
    changed_files: tuple[str, ...]
    finding_count: int
    database_ok: bool
    git_available: bool
    git_status: str


class StartTaskToolPayload(TypedDict):
    ok: bool
    query: str
    relevant_files: tuple[str, ...]
    relevant_symbols: tuple[str, ...]
    related_tests: tuple[str, ...]
    open_findings: tuple[dict[str, str], ...]
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None
    warnings: tuple[str, ...]
    confidence: str
    next_tools: tuple[str, ...]
    bootstrap: BootstrapNote


class ResumeTaskToolPayload(TypedDict):
    ok: bool
    session_id: str
    status: str
    summary: str
    active_findings: tuple[dict[str, str], ...]
    verified_findings: tuple[dict[str, str], ...]
    recently_touched_files: tuple[str, ...]
    recent_tools: tuple[str, ...]
    ratchet: RatchetStatus
    next_tools: tuple[str, ...]


def register_repo_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "RESUME work after losing context (e.g. a compaction): "
            "reconstructs a bounded session brief purely from persisted state — "
            "active/last findings, what's already verified, the health-ratchet "
            "baseline status, recently touched files, the recent tool trail, and "
            "the recommended next call. Deterministic; reads no analyzed source; "
            "bounded output. e.g. resume_task(session_id='default')."
        ),
    )(resume_task)

    _ = mcp.tool(
        description=(
            "Call FIRST when beginning a task: a bounded brief of relevant "
            "files, key symbols, related tests, in-scope findings, index "
            "freshness, auto-refresh and auto-bootstrap status, warnings, "
            "confidence, and the next calls to make so you avoid broad greps and "
            "round trips. start_task opens fresh work on a task; use answer_pack "
            "instead when you have a specific question to fit in a token budget. "
            "e.g. start_task(query='add rate limiting to the API'). Read-only "
            "for source; bounded output."
        ),
    )(start_task)

    _ = mcp.tool(
        description=(
            "Bounded repository map before broad grep or large reads: returns "
            "paths and counts, never source content. Read-only. e.g. "
            "get_repo_map(repo='.')."
        ),
    )(get_repo_map)

    _ = mcp.tool(
        description=(
            "Bounded repository status before broad grep or large reads: index "
            "freshness, changed files, and finding counts. Read-only; creates or "
            "modifies no CodeScent state. e.g. get_repo_status(repo='.')."
        ),
    )(get_repo_status)


def start_task(
    query: str,
    repo: str = ".",
    focus_path: str | None = None,
    focus_symbol: str | None = None,
) -> StartTaskToolPayload:
    return _task_brief_payload(
        TaskBriefService(repo).start_task(
            query,
            focus_path=focus_path,
            focus_symbol=focus_symbol,
        ),
    )


def resume_task(
    repo: str = ".",
    session_id: str = "default",
    project_id: str | None = None,
) -> ResumeTaskToolPayload:
    resolved_project_id = project_id or f"repo:{resolve_repo_root(repo).as_posix()}"
    return _resume_brief_payload(
        SessionResumeService(repo).resume_task(
            project_id=resolved_project_id,
            session_id=session_id,
        ),
    )


def _resume_brief_payload(brief: ResumeBrief) -> ResumeTaskToolPayload:
    return {
        "ok": True,
        "session_id": brief.session_id,
        "status": brief.status,
        "summary": brief.summary,
        "active_findings": brief.active_findings,
        "verified_findings": brief.verified_findings,
        "recently_touched_files": brief.recently_touched_files,
        "recent_tools": brief.recent_tools,
        "ratchet": brief.ratchet,
        "next_tools": brief.next_tools,
    }


def get_repo_map(repo: str = ".") -> RepoMapToolPayload:
    repo_root = resolve_repo_root(repo)
    config = ConfigService(repo_root).load()
    inventory = build_file_inventory(repo_root, config=config)

    return {
        "ok": True,
        "read_only": True,
        "file_count": len(inventory),
        "test_file_count": sum(1 for item in inventory if item.is_test),
        "languages": _language_counts(tuple(item.language for item in inventory)),
        "top_level": _top_level(tuple(item.path for item in inventory)),
        "entrypoints": _entrypoints(tuple(item.path for item in inventory)),
        "sample_files": tuple(item.path for item in inventory[:SAMPLE_FILE_LIMIT]),
    }


def _task_brief_payload(brief: TaskBrief) -> StartTaskToolPayload:
    return {
        "ok": True,
        "query": brief.query,
        "relevant_files": brief.relevant_files,
        "relevant_symbols": brief.relevant_symbols,
        "related_tests": brief.related_tests,
        "open_findings": brief.open_findings,
        "index_fresh": brief.index_fresh,
        "index_was_stale": brief.index_was_stale,
        "auto_refreshed": brief.auto_refreshed,
        "changed_files": brief.changed_files,
        "refresh_error": brief.refresh_error,
        "warnings": brief.warnings,
        "confidence": brief.confidence,
        "next_tools": brief.next_tools,
        "bootstrap": brief.bootstrap,
    }


def get_repo_status(repo: str = ".") -> RepoStatusToolPayload:
    repo_root = resolve_repo_root(repo)
    config = ConfigService(repo_root).load()
    inventory_hashes = {
        item.path: item.hash for item in build_file_inventory(repo_root, config=config)
    }
    database_path = repo_root / ".codescent" / "index.sqlite"
    stored_hashes = _stored_hashes(database_path)
    changed_files = _changed_files(inventory_hashes, stored_hashes)
    git_state = detect_git_state(repo_root)

    return {
        "ok": True,
        "read_only": True,
        "index_fresh": (
            database_path.exists()
            and len(changed_files) == 0
            and len(stored_hashes) == len(inventory_hashes)
        ),
        "indexed_files": len(stored_hashes),
        "changed_files": changed_files[:CHANGED_FILE_LIMIT],
        "finding_count": _finding_count(database_path),
        "database_ok": database_path.exists(),
        "git_available": git_state.available,
        "git_status": git_state.status,
    }


def _language_counts(languages: tuple[str, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for language in languages:
        counts[language] = counts.get(language, 0) + 1
    return dict(sorted(counts.items()))


def _top_level(paths: tuple[str, ...]) -> tuple[str, ...]:
    names = {path.split("/", maxsplit=1)[0] for path in paths}
    return tuple(sorted(names))


def _entrypoints(paths: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(path for path in paths if Path(path).name in ENTRYPOINT_NAMES)


def _stored_hashes(database_path: Path) -> dict[str, str]:
    if not database_path.exists():
        return {}
    try:
        with closing(sqlite3.connect(database_path)) as connection:
            rows: list[tuple[str, str]] = connection.execute(
                "select path, hash from files",
            ).fetchall()
    except sqlite3.DatabaseError:
        return {}
    return dict(rows)


def _finding_count(database_path: Path) -> int:
    if not database_path.exists():
        return 0
    try:
        with closing(sqlite3.connect(database_path)) as connection:
            rows: list[tuple[int]] = connection.execute(
                "select id from findings",
            ).fetchall()
    except sqlite3.DatabaseError:
        return 0
    return len(rows)


def _changed_files(
    inventory_hashes: dict[str, str],
    stored_hashes: dict[str, str],
) -> tuple[str, ...]:
    modified_files = tuple(
        path
        for path, file_hash in inventory_hashes.items()
        if stored_hashes.get(path) != file_hash
    )
    deleted_files = tuple(
        path for path in stored_hashes if path not in inventory_hashes
    )
    return (*modified_files, *deleted_files)
