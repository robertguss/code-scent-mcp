import hashlib
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
import scripts.prove_source_read_only as source_safety
import scripts.smoke_lx_data_lake as lx_smoke
from pydantic import TypeAdapter
from scripts.prove_source_read_only import prove_source_read_only

from codescent.engine.inventory import build_file_inventory
from codescent.mcp.context_tools import find_symbol
from codescent.mcp.finding_tools import get_smell_report, scan_code_health
from codescent.mcp.planning_tools import suggest_tests
from codescent.mcp.result_tools import retrieve_result
from codescent.mcp.search_tools import search_content, search_files
from codescent.mcp.session_stats_tools import context_stats
from codescent.services.result_store import ResultStoreService
from codescent.services.subjective_review import (
    FakeSubjectiveReviewProvider,
    SubjectiveReviewService,
)
from codescent.smoke.lx_data_lake_contract import JsonValue
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import SessionEventRepository

JSON_PAYLOAD = TypeAdapter(dict[str, JsonValue])
TASK16_SENTINEL = "FAKE_TASK16_SENTINEL_DO_NOT_LEAK"


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
    if result.returncode != 0 and "Google Chrome is required" in result.stderr:
        pytest.skip("Google Chrome is required for dashboard smoke")
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


def test_context_optimization_tools_are_no_network_and_source_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_symbol_repo(repo, count=24)
    before = _source_hashes(repo)
    attempts: list[str] = []

    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        _ = args, kwargs
        attempts.append("socket")
        message = "network disabled"
        raise AssertionError(message)

    monkeypatch.setattr(socket, "socket", blocked_socket)

    symbol_payload = find_symbol(
        "handler",
        repo=str(repo),
        limit=24,
        project_id="project-task16",
        session_id="session-task16",
    )
    result_id = symbol_payload.get("original_result_id")
    assert isinstance(result_id, str)

    retrieved = retrieve_result(
        result_id,
        repo=str(repo),
        mode="exact",
        limit=30,
        project_id="project-task16",
        session_id="session-task16",
    )
    stats = context_stats(
        "session-task16",
        repo=str(repo),
        project_id="project-task16",
    )

    assert symbol_payload.get("ok") is True
    assert retrieved["kind"] == "retrieved_result"
    assert stats["tool_calls"] == 1
    assert stats["summarized_results"] == 1
    assert stats["retrievals"] == 1
    assert attempts == []
    assert _source_hashes(repo) == before


def test_retrieve_result_file_filter_cannot_path_traverse_or_read_filesystem(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    filesystem_secret = tmp_path / "filesystem-secret.txt"
    _ = filesystem_secret.write_text(f"filesystem {TASK16_SENTINEL}\n")
    stored_id = _store_sensitive_result(repo)

    exact = retrieve_result(stored_id, repo=str(repo), mode="exact", limit=10)
    absolute_filter = retrieve_result(
        stored_id,
        repo=str(repo),
        mode="filtered",
        file=str(filesystem_secret),
        limit=10,
        project_id="project-task16",
        session_id="session-path-filter",
    )
    traversal_filter = retrieve_result(
        stored_id,
        repo=str(repo),
        mode="filtered",
        file="../../filesystem-secret.txt",
        limit=10,
        project_id="project-task16",
        session_id="session-path-filter",
    )
    stored_path_filter = retrieve_result(
        stored_id,
        repo=str(repo),
        mode="filtered",
        file="src/safe.py",
        limit=10,
    )

    exact_json = json.dumps(exact, sort_keys=True, default=str)
    absolute_json = json.dumps(absolute_filter, sort_keys=True, default=str)
    traversal_json = json.dumps(traversal_filter, sort_keys=True, default=str)
    stored_path_json = json.dumps(stored_path_filter, sort_keys=True, default=str)
    event_json = _session_events_json(
        repo,
        project_id="project-task16",
        session_id="session-path-filter",
    )

    assert TASK16_SENTINEL in exact_json
    assert absolute_filter["items"] == ()
    assert traversal_filter["items"] == ()
    assert absolute_filter["remaining_count"] == 0
    assert traversal_filter["remaining_count"] == 0
    assert TASK16_SENTINEL in stored_path_json
    assert TASK16_SENTINEL not in absolute_json
    assert TASK16_SENTINEL not in traversal_json
    assert TASK16_SENTINEL not in event_json
    assert str(filesystem_secret) not in event_json
    assert "../../filesystem-secret.txt" not in event_json


def test_context_stats_and_events_do_not_leak_raw_sentinel_content(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    stored_id = _store_sensitive_result(repo)

    exact = retrieve_result(
        stored_id,
        repo=str(repo),
        mode="exact",
        limit=10,
        project_id="project-task16",
        session_id="session-no-leak",
    )
    stats = context_stats(
        "session-no-leak",
        repo=str(repo),
        project_id="project-task16",
    )

    exact_json = json.dumps(exact, sort_keys=True, default=str)
    stats_json = json.dumps(stats, sort_keys=True, default=str)
    event_json = _session_events_json(
        repo,
        project_id="project-task16",
        session_id="session-no-leak",
    )

    assert TASK16_SENTINEL in exact_json
    assert TASK16_SENTINEL not in stats_json
    assert TASK16_SENTINEL not in event_json
    assert "stored raw" not in stats_json
    assert "stored raw" not in event_json
    assert "source_content" not in stats_json
    assert "source_content" not in event_json


def test_retrieve_result_invalid_and_missing_ids_have_deterministic_json_errors(
    tmp_path: Path,
) -> None:
    missing = retrieve_result("ctx_0000000000000000", repo=str(tmp_path))
    invalid = retrieve_result("../secret.txt", repo=str(tmp_path))
    combined = json.dumps([missing, invalid], sort_keys=True, default=str)

    assert missing == {
        "kind": "result_store_error",
        "code": "missing_result",
        "message": "Stored result ID was not found.",
        "result_id": "ctx_0000000000000000",
        "retryable": False,
    }
    assert invalid == {
        "kind": "result_store_error",
        "code": "invalid_result_id",
        "message": "Result ID must be an opaque ctx_ identifier.",
        "result_id": "../secret.txt",
        "retryable": False,
    }
    assert "Traceback" not in combined
    assert "LookupError" not in combined


def _source_hashes(repo: Path) -> dict[str, str]:
    return {
        item.path: hashlib.sha256((repo / item.path).read_bytes()).hexdigest()
        for item in build_file_inventory(repo)
    }


def _write_symbol_repo(
    repo: Path,
    *,
    count: int,
    sentinel: str | None = None,
) -> None:
    source = repo / "src" / "many.py"
    source.parent.mkdir(parents=True)
    secret_line = ""
    if sentinel is not None:
        secret_line = f"TASK16_PRIVATE_NOTE = {sentinel!r}\n\n"
    _ = source.write_text(
        secret_line
        + "\n".join(
            f"def handler_{index}() -> int:\n    return {index}\n"
            for index in range(count)
        ),
    )


def _store_sensitive_result(repo: Path) -> str:
    stored = ResultStoreService(repo).store_result(
        project_id="project-task16",
        tool_name="symbol_search",
        input_payload={"query": "safe"},
        raw_result={
            "results": [
                {
                    "type": "definition",
                    "path": "src/safe.py",
                    "name": "safe_handler",
                    "snippet": f"stored raw {TASK16_SENTINEL}",
                },
            ],
        },
        summary={"items": [{"type": "summary", "count": 1}]},
    )
    return stored.id


def _session_events_json(repo: Path, *, project_id: str, session_id: str) -> str:
    events = SessionEventRepository(
        RepositoryStorage(initialize_storage(repo)),
    ).list_events(project_id=project_id, session_id=session_id)
    payloads = [event.payload for event in events]
    return json.dumps(cast("object", payloads), sort_keys=True, default=str)
