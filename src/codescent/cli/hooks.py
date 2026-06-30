"""Claude Code hook entrypoints exposed as codescent CLI subcommands.

Three commands, all designed for the never-block / read-only contract of the
grep-injection hook:

* ``hook-augment`` (U4) — PreToolUse enrichment for Grep/Glob/Bash searches.
* ``hook-reindex`` (U5) — incremental reindex for SessionStart / PostToolUse.
* ``install-hook`` (U6) — register/remove the hooks in a Claude Code settings file.

Module-level imports are kept light on purpose: every heavy dependency is
imported lazily inside the command body so a cold ``codescent hook-augment``
invocation does not pay codescent's full service-import cost (R20).
"""

from __future__ import annotations

import contextlib
import json
import shutil
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Final, cast

import typer

if TYPE_CHECKING:
    from collections.abc import Generator

# Cap stdin so a malformed or hostile payload cannot make the hook read forever
# (R23). Hook JSON for a search is tiny; 64 KiB is generous headroom.
_STDIN_CAP: Final = 64 * 1024
# Self-imposed wall-clock deadline so the hook cannot delay a search beyond a
# small budget, independent of the settings-level timeout (R13).
_DEADLINE_SECONDS: Final = 1.5
# Marker that a repo is onboarded; its presence gates all hook work (R16/AE4).
_INDEX_DB: Final = Path(".codescent") / "index.sqlite"


@contextlib.contextmanager
def _deadline(seconds: float) -> Generator[None]:
    """Best-effort wall-clock bound via SIGALRM; a no-op where unavailable."""
    if not hasattr(signal, "setitimer"):
        yield
        return

    def _raise(_signum: int, _frame: object) -> None:
        raise TimeoutError

    try:
        previous = signal.signal(signal.SIGALRM, _raise)
    except ValueError:
        # Not the main thread — skip the deadline rather than crash.
        yield
        return
    _ = signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        _ = signal.setitimer(signal.ITIMER_REAL, 0)
        _ = signal.signal(signal.SIGALRM, previous)


def _read_hook_stdin() -> dict[str, object] | None:
    raw = sys.stdin.read(_STDIN_CAP + 1)
    if not raw or len(raw) > _STDIN_CAP:
        return None
    payload = cast("object", json.loads(raw))
    if isinstance(payload, dict):
        return cast("dict[str, object]", payload)
    return None


def _gate_and_extract(tool_name: str, tool_input: dict[str, object]) -> str | None:
    """Return the usable search pattern for this tool call, or ``None``.

    Applies the Bash search-detection gate (R2) and the pattern-usability rule
    (R3) using only string inspection — the command is never executed (R22).
    """
    if tool_name not in {"Bash", "Grep", "Glob"}:
        return None
    from codescent.cli.hook_support import (  # noqa: PLC0415 - lazy for cold start (R20)
        extract_pattern,
        usable_pattern,
    )

    # For Bash, extract_pattern returns None for non-search commands — it gates on
    # the search-binary set internally — so no separate detect_search_command
    # pre-check is needed, and the command is tokenized only once.
    return usable_pattern(extract_pattern(tool_name, tool_input))


def hook_augment() -> None:
    """PreToolUse entrypoint: print codescent enrichment, never block (R11/R12).

    Any failure — malformed input, no usable pattern, unindexed repo, timeout,
    or any exception — results in exit 0 with no output, so the intercepted
    Grep/Glob/Bash call always runs unchanged.
    """
    with contextlib.suppress(Exception), _deadline(_DEADLINE_SECONDS):
        _run_hook_augment()


def _run_hook_augment() -> None:
    payload = _read_hook_stdin()
    if payload is None:
        return
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    cwd = payload.get("cwd")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return
    repo_root = Path(cwd) if isinstance(cwd, str) and cwd else Path()

    pattern = _gate_and_extract(tool_name, cast("dict[str, object]", tool_input))
    if pattern is None:
        return

    # Enrichment only rides an already-onboarded repo; never create state (R16/AE4).
    if not (repo_root / _INDEX_DB).exists():
        return

    from codescent.services.hook_payload import (  # noqa: PLC0415 - lazy (R20)
        build_payload,
    )

    context = build_payload(repo_root, pattern)
    if context:
        _emit_context(context)


def _emit_context(context: str) -> None:
    output = json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": context,
            },
        },
    )
    _ = sys.stdout.write(output + "\n")


def hook_reindex() -> None:
    """SessionStart / PostToolUse entrypoint: incremental reindex, never fail loud.

    Registered with ``async: true`` so it never delays the agent (R14/R15). It
    guards on an existing index and does nothing in an un-onboarded repo, so it
    never creates ``.codescent/`` state implicitly (R16). Any error exits 0.
    """
    with contextlib.suppress(Exception):
        _run_hook_reindex()


def _run_hook_reindex() -> None:
    payload = _read_hook_stdin()
    cwd = payload.get("cwd") if payload is not None else None
    repo_root = Path(cwd) if isinstance(cwd, str) and cwd else Path()

    # Never create state in a repo the user never onboarded (R16). Reuse the
    # existing index only; do not call initialize_storage.
    if not (repo_root / _INDEX_DB).exists():
        return

    from codescent.services.repo_index import (  # noqa: PLC0415 - lazy (R20)
        RepoIndexService,
    )

    # Incremental by hash diff — covers both the session-start pass and the
    # per-edit touched-file pass; the specific edited path needs no special case.
    _ = RepoIndexService(repo_root).index_repo(full=False)


def _settings_path(*, is_global: bool) -> Path:
    base = Path.home() if is_global else Path.cwd()
    return base / ".claude" / "settings.json"


def _resolve_entrypoint() -> str:
    """Absolute path to the ``codescent`` binary, or the bare name as fallback.

    An absolute path is robust regardless of how Claude Code's ``sh -c`` PATH is
    set up; the bare name relies on ``codescent`` being on PATH at hook runtime.
    """
    return shutil.which("codescent") or "codescent"


def _load_settings(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    loaded = cast("object", json.loads(path.read_text(encoding="utf-8")))
    if isinstance(loaded, dict):
        return cast("dict[str, object]", loaded)
    return {}


def _write_settings(path: Path, settings: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(settings, indent=2) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    _ = tmp.write_text(serialized, encoding="utf-8")
    try:
        _ = tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)  # don't leave a stale .tmp behind
        raise


def install_hook(
    *,
    is_global: Annotated[
        bool,
        typer.Option("--global", help="Write ~/.claude/settings.json instead of cwd."),
    ] = False,
    remove: Annotated[
        bool,
        typer.Option("--remove", help="Remove codescent's hook entries."),
    ] = False,
) -> None:
    """Register (or remove) codescent's search-enrichment hooks in settings.json."""
    from codescent.services.hook_install import (  # noqa: PLC0415 - lazy (R20)
        merge_codescent_hooks,
        remove_codescent_hooks,
    )

    target = _settings_path(is_global=is_global)
    settings = _load_settings(target)
    if remove:
        updated = remove_codescent_hooks(settings)
        action = "Removed codescent hooks from"
    else:
        updated = merge_codescent_hooks(settings, _resolve_entrypoint())
        action = "Installed codescent hooks in"
    _write_settings(target, updated)
    typer.echo(f"{action} {target}")


def register_hook_commands(app: typer.Typer) -> None:
    _ = app.command(name="hook-augment")(hook_augment)
    _ = app.command(name="hook-reindex")(hook_reindex)
    _ = app.command(name="install-hook")(install_hook)
