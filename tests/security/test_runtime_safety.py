import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest
import scripts.prove_source_read_only as source_safety
import scripts.smoke_lx_data_lake as lx_smoke
from pydantic import TypeAdapter
from scripts.prove_source_read_only import prove_source_read_only

from codescent.mcp.finding_tools import get_smell_report, scan_code_health
from codescent.mcp.planning_tools import suggest_tests
from codescent.mcp.search_tools import search_content, search_files
from codescent.services.subjective_review import (
    FakeSubjectiveReviewProvider,
    SubjectiveReviewService,
)
from codescent.smoke.lx_data_lake_contract import JsonValue

JSON_PAYLOAD = TypeAdapter(dict[str, JsonValue])


def test_mcp_tools_do_not_modify_source(tmp_path: Path) -> None:
    out = tmp_path / "read-only.json"

    payload = prove_source_read_only(
        repo=Path("tests/fixtures/python-basic"),
        out=out,
    )
    written = JSON_PAYLOAD.validate_json(out.read_text())

    assert payload["source_hashes_unchanged"] is True
    assert payload["changed_paths"] == []
    assert written["allowed_changed_root"] == ".codescent"
    assert written["network_attempts"] == 0


def test_source_read_only_proof_reports_false_when_tool_mutates_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("value = 1\n")

    def mutate_source(repo_path: Path) -> list[dict[str, JsonValue]]:
        _ = (repo_path / "src" / "pkg" / "app.py").write_text("value = 2\n")
        return []

    monkeypatch.setattr(source_safety, "_tool_calls", mutate_source)

    payload = prove_source_read_only(repo=repo, out=tmp_path / "proof.json")

    assert payload["ok"] is False
    assert payload["source_hashes_unchanged"] is False
    assert payload["changed_paths"] == ["src/pkg/app.py"]


def test_lx_smoke_reports_false_when_tool_mutates_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "lx_data_lake" / "cli.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("def main() -> None:\n    return None\n")

    def mutate_source(repo_path: Path) -> list[dict[str, JsonValue]]:
        _ = (repo_path / "src" / "lx_data_lake" / "cli.py").write_text(
            "def main() -> None:\n    print('changed')\n",
        )
        return []

    monkeypatch.setattr(lx_smoke, "_execute_tool_loop", mutate_source)

    payload = lx_smoke.run_smoke(repo=repo, out=tmp_path / "lx.json", dry_run=False)

    assert payload["ok"] is False
    assert payload["source_hashes_unchanged"] is False
    assert payload["changed_paths"] == ["src/lx_data_lake/cli.py"]


def test_core_scan_makes_no_network_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[str] = []

    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        _ = args, kwargs
        attempts.append("socket")
        message = "network disabled"
        raise AssertionError(message)

    monkeypatch.setattr(socket, "socket", blocked_socket)

    repo = "tests/fixtures/python-basic"
    shutil.rmtree(Path(repo) / ".codescent", ignore_errors=True)
    scan = scan_code_health(repo)
    files = search_files("workflow", repo=repo)
    content = search_content("pending-review", repo=repo)

    assert scan["ok"] is True
    assert files["results"]
    assert content["results"]
    assert attempts == []


def test_verification_commands_are_recommended_not_executed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = "tests/fixtures/python-basic"
    shutil.rmtree(Path(repo) / ".codescent", ignore_errors=True)
    _ = scan_code_health(repo)
    report = get_smell_report(repo)
    selected = next(
        finding["finding_id"]
        for finding in report["findings"]
        if finding["file_path"] == "src/acme_tasks/workflow.py"
    )
    assert isinstance(selected, str)

    def fail_if_subprocess_runs(
        *args: object,
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        _ = args, kwargs
        message = "target verification command executed"
        raise AssertionError(message)

    monkeypatch.setattr(subprocess, "run", fail_if_subprocess_runs)

    suggested = suggest_tests(selected, repo=repo)

    assert suggested["commands"]
    assert suggested["executes_in_v1"] is False


def test_subjective_review_is_disabled_by_default_and_uses_fake_provider_in_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[str] = []

    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        _ = args, kwargs
        attempts.append("socket")
        message = "network disabled"
        raise AssertionError(message)

    monkeypatch.setattr(socket, "socket", blocked_socket)

    repo = "tests/fixtures/python-basic"
    shutil.rmtree(Path(repo) / ".codescent", ignore_errors=True)
    disabled = SubjectiveReviewService(repo).review(provider_name="fake")
    enabled = SubjectiveReviewService(repo).review(
        provider_name="fake",
        provider=FakeSubjectiveReviewProvider(),
        allow_subjective=True,
    )

    assert disabled.enabled is False
    assert disabled.provider == "disabled"
    assert "disabled by default" in disabled.privacy_notice
    assert enabled.enabled is True
    assert enabled.provider == "fake"
    assert enabled.subjective_findings
    assert enabled.subjective_findings[0].subjective is True
    assert "CodeScent subjective review prompt" in enabled.prompt
    assert attempts == []


def test_dashboard_smoke_is_local_only_and_source_read_only(tmp_path: Path) -> None:
    out = tmp_path / "dashboard-smoke.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/smoke_dashboard.py",
            "--repo",
            "tests/fixtures/python-basic",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    payload = JSON_PAYLOAD.validate_json(out.read_text())

    assert result.returncode == 0
    assert payload["ok"] is True
    assert payload["external_requests"] == 0
    assert payload["changed_source_paths"] == []
    assert Path(str(payload["screenshot_path"])).is_file()
    cleanup = payload["cleanup"]
    exports = payload["exports"]
    assert isinstance(cleanup, dict)
    assert isinstance(exports, dict)
    json_export = exports["json"]
    markdown_export = exports["markdown"]
    assert cleanup["server_stopped"] is True
    assert isinstance(json_export, str)
    assert isinstance(markdown_export, str)
    assert json_export.endswith(".json")
    assert markdown_export.endswith(".md")
