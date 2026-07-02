"""The single state-write choke point (bead P3.7 / F9 / U7).

Every filesystem write of CodeScent state must resolve its target through
:func:`state_path`, which guarantees the path stays inside ``<repo>/.codescent``.
A traversal (``..``), an absolute part, or a symlink pointing out of the state
directory raises a structured error instead of writing outside the sandbox --
making "CodeScent only writes under .codescent" a runtime invariant, not just a
convention. (DB writes are already funnelled through write_transaction; this
closes the plain-file side.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codescent.core.errors import CodeScentError, ErrorCode, ErrorSeverity

if TYPE_CHECKING:
    from pathlib import Path

STATE_DIR_NAME = ".codescent"


def state_path(repo_root: Path, *parts: str) -> Path:
    """Resolve ``<repo_root>/.codescent/<parts>`` asserting it stays contained.

    Returns the resolved path (parent dirs are not created here). Raises
    :class:`CodeScentError` (``PATH_OUTSIDE_ROOT``) if the resolved target
    escapes the state directory -- via ``..``, an absolute part, or a symlink.
    """
    state_dir = (repo_root / STATE_DIR_NAME).resolve()
    target = state_dir.joinpath(*parts).resolve()
    if target != state_dir and not target.is_relative_to(state_dir):
        raise CodeScentError(
            code=ErrorCode.PATH_OUTSIDE_ROOT,
            message=(
                f"Refusing to write outside the CodeScent state directory: "
                f"{target} is not under {state_dir}."
            ),
            severity=ErrorSeverity.ERROR,
            details={"target": str(target), "state_dir": str(state_dir)},
        )
    return target
