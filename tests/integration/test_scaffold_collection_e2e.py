import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from codescent.mcp.planning_tools import suggest_tests
from codescent.services.code_health import CodeHealthService

LOGGER = logging.getLogger(__name__)


def test_scaffold_is_collected_by_pytest_without_a_fake_green(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    repo = _repo_with_smell(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = next(
        item for item in scan.finding_ids if item.startswith("python.todo_cluster")
    )
    LOGGER.info("e2e: using finding_id=%s", finding_id)

    payload = suggest_tests(finding_id, repo=str(repo), scaffold=True)
    scaffold = payload.get("scaffold")
    assert scaffold is not None, "expected an opt-in scaffold field, found none"
    LOGGER.info(
        "e2e: generated scaffold target module=%s symbol=%s file=%s",
        scaffold["module"],
        scaffold["symbol"],
        scaffold["filename"],
    )
    LOGGER.info("e2e: generated code:\n%s", scaffold["code"])

    gen_dir = tmp_path / "gen"
    gen_dir.mkdir()
    test_file = gen_dir / scaffold["filename"]
    _ = test_file.write_text(scaffold["code"], encoding="utf-8")

    env = dict(os.environ)
    # The skeleton imports the fixture package; expose it without installing.
    env["PYTHONPATH"] = str(repo / "src")

    # 1) Collection must succeed (no import/syntax error).
    collect = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            str(test_file),
        ],
        capture_output=True,
        text=True,
        cwd=gen_dir,
        env=env,
        check=False,
    )
    LOGGER.info(
        "e2e: collect-only -> expected rc=0, found rc=%d\nstdout:\n%s\nstderr:\n%s",
        collect.returncode,
        collect.stdout,
        collect.stderr,
    )
    assert collect.returncode == 0, "pytest failed to collect the generated skeleton"
    assert "error" not in collect.stdout.lower(), "collection reported an error"
    assert "1 test collected" in collect.stdout or "test collected" in collect.stdout

    # 2) Running it must NOT report a false-positive pass: the honest
    #    placeholder fails loudly until a real assertion replaces it.
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            str(test_file),
        ],
        capture_output=True,
        text=True,
        cwd=gen_dir,
        env=env,
        check=False,
    )
    LOGGER.info(
        "e2e: run -> expected non-zero rc (RED), found rc=%d\nstdout:\n%s\nstderr:\n%s",
        run.returncode,
        run.stdout,
        run.stderr,
    )
    assert run.returncode != 0, "placeholder must not pass (no fake green)"
    assert "1 failed" in run.stdout
    assert "passed" not in run.stdout
    assert "NotImplementedError" in run.stdout


def _repo_with_smell(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    test = repo / "tests" / "test_config.py"
    source.parent.mkdir(parents=True)
    test.parent.mkdir()
    _ = source.write_text(
        """SECRET_SENTINEL = "do not leak"
STATUS = "pending-review"


def load_config() -> str:
    # TODO: split config
    # FIXME: preserve compatibility
    # HACK: keep old queue name
    return STATUS
""",
    )
    _ = test.write_text(
        """from pkg.config import load_config


def test_load_config() -> None:
    assert load_config() == "pending-review"
""",
    )
    return repo
