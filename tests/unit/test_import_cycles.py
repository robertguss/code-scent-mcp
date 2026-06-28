from __future__ import annotations

from typing import TYPE_CHECKING

from codescent.core.models import ProjectConfig
from codescent.engine.packs import build_pack_registry
from codescent.engine.rules.import_cycles import (
    IMPORT_CYCLE_RULE_ID,
    scan_import_cycles,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write(repo: Path, relative: str, text: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text)


def _mod(target: str) -> str:
    return f"from {target} import marker\n\n\ndef marker() -> int:\n    return 1\n"


def _leaf() -> str:
    return "import json\n\n\ndef marker() -> str:\n    return json.dumps({})\n"


def test_three_module_cycle_yields_single_ordered_finding(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/pkg/__init__.py", "")
    _write(repo, "src/pkg/a.py", _mod("pkg.b"))
    _write(repo, "src/pkg/b.py", _mod("pkg.c"))
    _write(repo, "src/pkg/c.py", _mod("pkg.a"))

    findings = scan_import_cycles(repo)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == IMPORT_CYCLE_RULE_ID
    assert finding.severity == "warning"
    assert finding.file_path == "src/pkg/a.py"
    assert finding.evidence["cycle_size"] == 3
    assert (
        finding.evidence["cycle_path"]
        == "src/pkg/a.py -> src/pkg/b.py -> src/pkg/c.py -> src/pkg/a.py"
    )
    assert (
        finding.evidence["cycle_members"] == "src/pkg/a.py, src/pkg/b.py, src/pkg/c.py"
    )


def test_acyclic_repo_has_no_findings(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/pkg/__init__.py", "")
    _write(repo, "src/pkg/a.py", _mod("pkg.b"))
    _write(repo, "src/pkg/b.py", _mod("pkg.c"))
    _write(repo, "src/pkg/c.py", _leaf())

    assert scan_import_cycles(repo) == ()


def test_two_module_cycle_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/pkg/__init__.py", "")
    _write(repo, "src/pkg/a.py", _mod("pkg.b"))
    _write(repo, "src/pkg/b.py", _mod("pkg.a"))

    findings = scan_import_cycles(repo)

    assert len(findings) == 1
    assert (
        findings[0].evidence["cycle_path"]
        == "src/pkg/a.py -> src/pkg/b.py -> src/pkg/a.py"
    )


def test_reexport_self_loop_is_flagged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/pkg/__init__.py", "")
    _write(repo, "src/pkg/loop.py", "from pkg.loop import shared\n\nshared = 1\n")

    findings = scan_import_cycles(repo)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == IMPORT_CYCLE_RULE_ID
    assert finding.file_path == "src/pkg/loop.py"
    assert finding.evidence["cycle_size"] == 1
    assert finding.evidence["cycle_path"] == "src/pkg/loop.py -> src/pkg/loop.py"


def test_empty_repo_does_not_crash(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    assert scan_import_cycles(repo) == ()


def test_unparseable_file_degrades_gracefully(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/pkg/__init__.py", "")
    _write(repo, "src/pkg/broken.py", "def oops(:\n")
    _write(repo, "src/pkg/a.py", _mod("pkg.b"))
    _write(repo, "src/pkg/b.py", _leaf())

    assert scan_import_cycles(repo) == ()


def test_deterministic_ranking_largest_cycle_first(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/two/__init__.py", "")
    _write(repo, "src/two/p.py", _mod("two.q"))
    _write(repo, "src/two/q.py", _mod("two.r"))
    _write(repo, "src/two/r.py", _mod("two.p"))
    _write(repo, "src/one/__init__.py", "")
    _write(repo, "src/one/x.py", _mod("one.y"))
    _write(repo, "src/one/y.py", _mod("one.x"))

    findings = scan_import_cycles(repo)

    assert len(findings) == 2
    assert findings[0].evidence["cycle_size"] == 3
    assert findings[1].evidence["cycle_size"] == 2
    assert tuple(f.id for f in findings) == tuple(
        f.id for f in scan_import_cycles(repo)
    )


def test_limit_zero_returns_empty(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/pkg/__init__.py", "")
    _write(repo, "src/pkg/a.py", _mod("pkg.b"))
    _write(repo, "src/pkg/b.py", _mod("pkg.a"))

    assert scan_import_cycles(repo, limit=0) == ()


def test_rule_id_registered_in_pack_registry(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/pkg/__init__.py", "")
    _write(repo, "src/pkg/a.py", _mod("pkg.b"))
    _write(repo, "src/pkg/b.py", _mod("pkg.a"))

    registry = build_pack_registry(ProjectConfig())
    findings = registry.scan_rule_packs(repo)

    assert IMPORT_CYCLE_RULE_ID in {finding.rule_id for finding in findings}
