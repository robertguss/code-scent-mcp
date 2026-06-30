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
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from collections.abc import Generator

    import typer

# Cap stdin so a malformed or hostile payload cannot make the hook read forever
# (R23). Hook JSON for a search is tiny; 64 KiB is generous headroom.
_STDIN_CAP: Final = 64 * 1024
# Self-imposed wall-clock deadline so the hook cannot delay a search beyond a
# small budget, independent of the settings-level timeout (R13).
_DEADLINE_SECONDS: Final = 1.5


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
    from codescent.cli.hook_support import (  # noqa: PLC0415 - lazy for cold start (R20)
        detect_search_command,
        extract_pattern,
        usable_pattern,
    )

    if tool_name == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str) or not detect_search_command(command):
            return None
    elif tool_name not in {"Grep", "Glob"}:
        return None
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
    if not (repo_root / ".codescent" / "index.sqlite").exists():
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


def register_hook_commands(app: typer.Typer) -> None:
    _ = app.command(name="hook-augment")(hook_augment)
