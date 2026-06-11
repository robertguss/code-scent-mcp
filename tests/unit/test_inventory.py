from pathlib import Path

import pytest

from codescent.core.errors import CodeScentError, ErrorCode
from codescent.core.paths import normalize_repo_path
from codescent.engine.inventory import build_file_inventory


def test_default_excludes_skip_sensitive_and_generated_paths(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    included = repo / "src" / "app.py"
    excluded_paths = [
        repo / ".env",
        repo / ".codescent" / "state.py",
        repo / ".git" / "config",
        repo / ".venv" / "lib.py",
        repo / "__pycache__" / "app.pyc",
        repo / "data" / "records.py",
        repo / "generated" / "client.py",
        repo / "__generated__" / "schema.py",
        repo / "vendor" / "vendored.py",
        repo / "dist" / "bundle.py",
        repo / "build" / "generated.py",
        repo / "coverage" / "report.py",
        repo / "src" / "bundle.min.js",
    ]

    included.parent.mkdir(parents=True)
    _ = included.write_text("print('hello')\n")
    for path in excluded_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text("SHOULD_NOT_READ\n")

    paths = {item.path for item in build_file_inventory(repo)}

    assert paths == {"src/app.py"}


def test_rejects_path_traversal(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside.py"
    repo.mkdir()
    _ = outside.write_text("secret = True\n")

    with pytest.raises(CodeScentError) as error:
        _ = normalize_repo_path(repo, "../outside.py")

    assert error.value.code is ErrorCode.PATH_OUTSIDE_ROOT


def test_symlink_outside_root_is_not_followed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside.py"
    inside = repo / "src" / "inside.py"
    link = repo / "src" / "linked.py"

    inside.parent.mkdir(parents=True)
    _ = inside.write_text("value = 1\n")
    _ = outside.write_text("secret = True\n")
    _ = link.symlink_to(outside)

    paths = {item.path for item in build_file_inventory(repo)}

    assert paths == {"src/inside.py"}
