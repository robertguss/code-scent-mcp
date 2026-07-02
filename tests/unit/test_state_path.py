"""The state-write choke point (bead P3.7 / F9 / U7)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from codescent.core.errors import CodeScentError, ErrorCode
from codescent.storage import state_path

if TYPE_CHECKING:
    from pathlib import Path


def test_returns_path_under_state_dir(tmp_path: Path) -> None:
    result = state_path(tmp_path, "scan_cache.json")
    assert result == (tmp_path / ".codescent" / "scan_cache.json").resolve()


def test_nested_parts_stay_contained(tmp_path: Path) -> None:
    result = state_path(tmp_path, "sub", "cache.json")
    assert result == (tmp_path / ".codescent" / "sub" / "cache.json").resolve()


def test_traversal_part_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CodeScentError) as excinfo:
        _ = state_path(tmp_path, "../escape.txt")
    assert excinfo.value.code == ErrorCode.PATH_OUTSIDE_ROOT


def test_absolute_part_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CodeScentError) as excinfo:
        _ = state_path(tmp_path, "/etc/passwd")
    assert excinfo.value.code == ErrorCode.PATH_OUTSIDE_ROOT


def test_symlink_escaping_state_dir_is_rejected(tmp_path: Path) -> None:
    state_dir = tmp_path / ".codescent"
    state_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (state_dir / "link").symlink_to(outside)

    # The symlink resolves out of the state dir, so a write through it is refused.
    with pytest.raises(CodeScentError) as excinfo:
        _ = state_path(tmp_path, "link", "leak.json")
    assert excinfo.value.code == ErrorCode.PATH_OUTSIDE_ROOT
