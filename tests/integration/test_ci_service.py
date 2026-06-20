import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from shutil import which

import pytest

from codescent.core.models import (
    MaintainabilityThresholds,
    ProjectConfig,
    RatchetSettings,
)
from codescent.services.ci import CiService
from codescent.services.config import ConfigService

STRICT_CONFIG = ProjectConfig(thresholds=MaintainabilityThresholds.strict())


def _function_module(name: str, body_lines: int) -> str:
    body = "\n".join(f"    step_{index} = {index}" for index in range(body_lines))
    return f"def {name}() -> None:\n{body}\n"


def _repo(tmp_path: Path, source: str) -> Path:
    repo = tmp_path / "repo"
    module = repo / "src" / "pkg" / "config.py"
    module.parent.mkdir(parents=True)
    _ = module.write_text(source)
    ConfigService(repo).save(STRICT_CONFIG)
    return repo


def _write(repo: Path, source: str) -> None:
    _ = (repo / "src" / "pkg" / "config.py").write_text(source)


def test_update_baseline_records_counts_and_stable_keys(tmp_path: Path) -> None:
    # A 30-line function trips large_function (warning) under the strict profile.
    repo = _repo(tmp_path, _function_module("process", 30))

    result = CiService(repo).update_baseline()

    assert result.files_recorded >= 1
    assert result.finding_count > 0
    baseline_keys = _finding_baseline_keys(repo)
    assert baseline_keys
    assert any(key.startswith("python.large_function") for key in baseline_keys)


def test_ratchet_is_no_op_without_an_accepted_baseline(tmp_path: Path) -> None:
    repo = _repo(tmp_path, _function_module("process", 30))

    report = CiService(repo).run(threshold="high", ratchet=True)

    assert report.ratchet_enabled is True
    assert report.baseline_exists is False
    # No baseline accepted yet: the ratchet recommends accepting one, it does not
    # fail the build, even though the absolute risk level is high.
    assert report.ok is True
    assert report.new_finding_count == 0


def test_ratchet_blocks_a_new_warning_finding(tmp_path: Path) -> None:
    repo = _repo(tmp_path, _function_module("small", 2))
    service = CiService(repo)
    _ = service.update_baseline()

    # Introduce a new large function (warning) that was not in the baseline.
    _write(repo, _function_module("process", 30))
    report = service.run(threshold="high", ratchet=True)

    assert report.ok is False
    assert report.new_finding_count >= 1
    assert any(
        finding.rule_id == "python.large_function" and finding.severity == "warning"
        for finding in report.new_findings
    )


def test_ratchet_allows_a_new_info_finding_below_severity_threshold(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path, _function_module("small", 2))
    service = CiService(repo)
    _ = service.update_baseline()

    # A new TODO cluster is info-severity; the default gate is "warning".
    _write(
        repo,
        """def small() -> None:
    # TODO: a
    # FIXME: b
    # HACK: c
    return None
""",
    )
    report = service.run(threshold="high", ratchet=True)

    assert report.ok is True
    # The new info finding is still reported, just not blocking.
    assert report.new_finding_count >= 1


def test_ratchet_ignores_the_pre_existing_backlog(tmp_path: Path) -> None:
    repo = _repo(tmp_path, _function_module("process", 30))
    service = CiService(repo)
    _ = service.update_baseline()

    ratchet_report = service.run(threshold="high", ratchet=True)
    absolute_report = service.run(threshold="high")

    # The pre-existing warning is in the baseline: the ratchet passes...
    assert ratchet_report.ok is True
    assert ratchet_report.new_finding_count == 0
    assert ratchet_report.resolved_count == 0
    # ...even though the non-ratchet absolute gate fails on the same warning.
    assert absolute_report.ok is False


def test_ratchet_catches_a_swapped_finding_at_constant_count(tmp_path: Path) -> None:
    # Stable-key advantage: resolving one finding while adding a different one
    # keeps the per-file count constant, so the old count-based ratchet missed it.
    repo = _repo(tmp_path, _function_module("alpha", 30))
    service = CiService(repo)
    _ = service.update_baseline()

    _write(repo, _function_module("beta", 30))
    report = service.run(threshold="high", ratchet=True)

    assert report.ok is False
    assert report.new_finding_count >= 1
    assert report.resolved_count >= 1
    assert any(
        finding.rule_id == "python.large_function" for finding in report.new_findings
    )


def test_ratchet_net_health_gate_fails_on_net_negative_change(tmp_path: Path) -> None:
    repo = _repo(tmp_path, _function_module("small", 2))
    config = ProjectConfig(
        thresholds=MaintainabilityThresholds.strict(),
        ratchet=RatchetSettings(require_non_negative_net_health=True),
    )
    ConfigService(repo).save(config)
    service = CiService(repo)
    _ = service.update_baseline()

    # Add a new large function (net +1 finding, nothing resolved).
    _write(repo, _function_module("process", 30))
    report = service.run(threshold="high", ratchet=True)

    assert report.net_health_delta < 0
    assert report.ok is False


def test_ratchet_treats_a_pre_v8_baseline_as_stale_not_all_new(tmp_path: Path) -> None:
    # Simulate a baseline accepted before schema v8: health_baseline is populated
    # but finding_baseline is empty. The ratchet must not treat the whole backlog
    # as new (which would fail CI) — it should no-op and flag the baseline stale.
    repo = _repo(tmp_path, _function_module("process", 30))
    service = CiService(repo)
    _ = service.update_baseline()
    _simulate_pre_v8_baseline(repo)

    report = service.run(threshold="high", ratchet=True)

    assert report.baseline_exists is True
    assert report.baseline_stale is True
    assert report.new_finding_count == 0
    assert report.ok is True


@pytest.mark.skipif(which("git") is None, reason="git is required for --base scoping")
def test_ratchet_base_ref_scopes_to_changed_files(tmp_path: Path) -> None:
    repo = _repo(tmp_path, _function_module("small", 2))
    other = repo / "src" / "pkg" / "other.py"
    _ = other.write_text(_function_module("tiny", 2))
    _git(repo, "init")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "base")

    service = CiService(repo)
    _ = service.update_baseline()

    # Only config.py grows a new warning; other.py is untouched.
    _write(repo, _function_module("process", 30))
    report = service.run(threshold="high", ratchet=True, base_ref="HEAD")

    assert report.base_ref == "HEAD"
    assert report.ok is False
    assert {finding.file_path for finding in report.new_findings} == {
        "src/pkg/config.py",
    }


def _git(repo: Path, *args: str) -> None:
    git_path = which("git")
    assert git_path is not None
    _ = subprocess.run(
        [git_path, "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _simulate_pre_v8_baseline(repo: Path) -> None:
    # Pre-v8 baselines populated only health_baseline (no stable keys, no marker).
    with closing(sqlite3.connect(repo / ".codescent" / "index.sqlite")) as connection:
        _ = connection.execute("delete from finding_baseline")
        _ = connection.execute("delete from baseline_meta")
        connection.commit()


def _finding_baseline_keys(repo: Path) -> tuple[str, ...]:
    with closing(sqlite3.connect(repo / ".codescent" / "index.sqlite")) as connection:
        rows: list[tuple[str]] = connection.execute(
            "select stable_key from finding_baseline",
        ).fetchall()
    return tuple(key for (key,) in rows)
