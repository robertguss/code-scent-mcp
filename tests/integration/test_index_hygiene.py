"""Index hygiene: .omo/ exclusion + .codescentignore (bead P3.2 / U2).

The index and the generic literal pack must reflect real source, not
tool byproduct: .omo/ tool state is never indexed, and a repo-root
.codescentignore removes matching files from both the inventory and the
generic pack -- through the single shared matcher.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codescent.core.models import ProjectConfig
from codescent.engine.inventory import build_file_inventory
from codescent.engine.packs_generic import generic_pack_files

if TYPE_CHECKING:
    from pathlib import Path


def _write(path: Path, text: str = "x = 1\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")


def _paths(repo: Path) -> set[str]:
    return {item.path for item in build_file_inventory(repo)}


def test_omo_dir_is_not_indexed_or_scanned(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "real.py")
    _write(tmp_path / ".omo" / "evidence" / "foo.py")
    _write(tmp_path / ".omo" / "evidence" / "foo.json", '{"ok": true}\n')

    inventory = _paths(tmp_path)
    generic = set(generic_pack_files(tmp_path, ProjectConfig()))

    assert "src/real.py" in inventory
    assert not any(p.startswith(".omo/") for p in inventory)
    # The generic literal rule must not scan .omo/*.json either.
    assert not any(p.startswith(".omo/") for p in generic)


def test_codescentignore_glob_excludes_matching_files(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "keep.py")
    _write(tmp_path / "docs" / "generated" / "api.py")
    _write(tmp_path / "docs" / "generated" / "nested" / "more.py")
    _write(tmp_path / ".codescentignore", "docs/generated/**\n")

    inventory = _paths(tmp_path)

    assert "src/keep.py" in inventory
    assert not any(p.startswith("docs/generated/") for p in inventory)


def test_codescentignore_matching_nothing_is_a_noop(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "keep.py")
    _write(tmp_path / ".codescentignore", "no/such/path/**\n\n# a comment\n")

    inventory = _paths(tmp_path)

    assert "src/keep.py" in inventory


def test_absent_codescentignore_leaves_behavior_unchanged(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.py")
    _write(tmp_path / "src" / "b.py")

    assert _paths(tmp_path) == {"src/a.py", "src/b.py"}


def test_codescentignore_also_excludes_from_generic_pack(tmp_path: Path) -> None:
    _write(tmp_path / "data.json", '{"ok": true}\n')
    _write(tmp_path / "reports" / "out.json", '{"ok": true}\n')
    _write(tmp_path / ".codescentignore", "reports/**\n")

    generic = set(generic_pack_files(tmp_path, ProjectConfig()))

    assert "data.json" in generic
    assert not any(p.startswith("reports/") for p in generic)
