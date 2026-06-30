"""Non-destructive Claude Code ``settings.json`` merge for codescent hooks (U6).

Pure dict transforms: build codescent's hook entries, merge them into an
existing settings object without disturbing unrelated hooks or keys (R17), and
strip exactly codescent's entries on ``--remove`` (R18). Codescent handlers are
identified by the codescent subcommand in their ``command`` string, so removal
never touches a third party's hook.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Final, cast

# Bash command prefixes that the native ``if``-gate wakes the augment hook for
# (KTD3); non-search Bash never spawns the Python entrypoint.
_SEARCH_GATES: Final = ("rg", "grep", "ripgrep", "ag")
# Backstop ceiling for the synchronous augment hook (KTD2); reindex is async.
_AUGMENT_TIMEOUT_SECONDS: Final = 5
# Substrings that mark a handler as codescent's own (idempotent install/remove).
_CODESCENT_SUBCOMMANDS: Final = ("hook-augment", "hook-reindex")

type Settings = dict[str, object]
type Group = dict[str, object]


def _command(
    command: str,
    *,
    timeout: int | None = None,
    is_async: bool = False,
    condition: str | None = None,
) -> dict[str, object]:
    handler: dict[str, object] = {"type": "command", "command": command}
    if condition is not None:
        handler["if"] = condition
    if timeout is not None:
        handler["timeout"] = timeout
    if is_async:
        handler["async"] = True
    return handler


def codescent_hook_groups(entrypoint: str) -> dict[str, list[Group]]:
    """The hook groups codescent registers, keyed by event name."""
    augment = f"{entrypoint} hook-augment"
    reindex = f"{entrypoint} hook-reindex"
    return {
        "PreToolUse": [
            {
                "matcher": "Grep|Glob",
                "hooks": [_command(augment, timeout=_AUGMENT_TIMEOUT_SECONDS)],
            },
            {
                "matcher": "Bash",
                "hooks": [
                    _command(
                        augment,
                        timeout=_AUGMENT_TIMEOUT_SECONDS,
                        condition=f"Bash({gate} *)",
                    )
                    for gate in _SEARCH_GATES
                ],
            },
        ],
        "PostToolUse": [
            {"matcher": "Edit|Write", "hooks": [_command(reindex, is_async=True)]},
        ],
        "SessionStart": [
            {"hooks": [_command(reindex, is_async=True)]},
        ],
    }


def _is_codescent_handler(handler: object) -> bool:
    if not isinstance(handler, dict):
        return False
    command = cast("dict[str, object]", handler).get("command")
    return isinstance(command, str) and any(
        sub in command for sub in _CODESCENT_SUBCOMMANDS
    )


def _strip_event_groups(groups: list[object]) -> list[object]:
    kept: list[object] = []
    for group in groups:
        if not isinstance(group, dict):
            kept.append(group)
            continue
        group_map = cast("dict[str, object]", group)
        handlers = group_map.get("hooks")
        if not isinstance(handlers, list):
            kept.append(group_map)
            continue
        handler_list = cast("list[object]", handlers)
        retained = [h for h in handler_list if not _is_codescent_handler(h)]
        if not retained:
            # All handlers were ours -> drop the group; keep an already-empty,
            # non-ours group untouched.
            if len(handler_list) == 0:
                kept.append(group_map)
            continue
        if len(retained) != len(handler_list):
            kept.append({**group_map, "hooks": retained})
        else:
            kept.append(group_map)
    return kept


def remove_codescent_hooks(settings: Settings) -> Settings:
    """Return ``settings`` with codescent's hook handlers stripped (R18).

    Drops a group only when every handler in it was codescent's; trims mixed
    groups; preserves all unrelated groups, events, and top-level keys.
    """
    result = deepcopy(settings)
    hooks = result.get("hooks")
    if not isinstance(hooks, dict):
        return result
    hooks_map = cast("dict[str, object]", hooks)
    for event in list(hooks_map.keys()):
        groups = hooks_map.get(event)
        if not isinstance(groups, list):
            continue
        kept_groups = _strip_event_groups(cast("list[object]", groups))
        if kept_groups:
            hooks_map[event] = kept_groups
        else:
            del hooks_map[event]
    if not hooks_map:
        del result["hooks"]
    return result


def merge_codescent_hooks(settings: Settings, entrypoint: str) -> Settings:
    """Merge codescent's hooks into ``settings`` non-destructively (R17).

    Idempotent: any prior codescent entries are removed first, so re-running
    install never stacks duplicates. Unrelated hooks and keys are preserved.
    """
    result = remove_codescent_hooks(settings)
    hooks = result.get("hooks")
    if isinstance(hooks, dict):
        hooks_map = cast("dict[str, object]", hooks)
    else:
        hooks_map = {}
        result["hooks"] = hooks_map
    for event, groups in codescent_hook_groups(entrypoint).items():
        existing = hooks_map.get(event)
        if isinstance(existing, list):
            cast("list[object]", existing).extend(groups)
        else:
            hooks_map[event] = list(groups)
    return result
