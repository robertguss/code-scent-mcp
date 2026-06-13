from __future__ import annotations

from typing import TYPE_CHECKING

from tests.integration.dashboard_http import JsonObject, get_json, get_text, post_json

from codescent.dashboard.server import start_dashboard_server
from codescent.services.code_health import CodeHealthService
from codescent.storage.schema import SCHEMA_VERSION

if TYPE_CHECKING:
    from pathlib import Path


def test_dashboard_binds_loopback_and_serves_local_read_api(tmp_path: Path) -> None:
    repo = _repo_with_finding(tmp_path)
    _ = CodeHealthService(repo).scan()

    server = start_dashboard_server(repo, port=0)
    try:
        assert server.host == "127.0.0.1"
        status = get_json(f"{server.base_url}/api/status")
        findings = get_json(f"{server.base_url}/api/findings")
        progress = get_json(f"{server.base_url}/api/progress")
        rules = get_json(f"{server.base_url}/api/rules")
        report = get_json(f"{server.base_url}/api/reports")
        export = get_json(f"{server.base_url}/api/exports")
    finally:
        server.shutdown()

    assert status.status == 200
    assert status.content_type.startswith("application/json")
    assert status.payload["read_only"] is True
    assert status.payload["bind_host"] == "127.0.0.1"
    assert findings.payload["read_only"] is True
    assert _int_field(progress.payload, "total_findings") >= 1
    assert rules.payload["read_only"] is True
    assert _int_field(report.payload, "open_count") >= 1
    assert export.payload["format"] == "json"


def test_dashboard_updates_rule_config_inside_codescent_only(tmp_path: Path) -> None:
    repo = _repo_with_finding(tmp_path)
    source_path = repo / "src" / "pkg" / "config.py"
    before_source = source_path.read_text()
    _ = CodeHealthService(repo).scan()

    server = start_dashboard_server(repo, port=0)
    try:
        response = post_json(
            f"{server.base_url}/api/rules",
            {"enabled_rule_packs": ["python-maintainability"]},
        )
        rules = get_json(f"{server.base_url}/api/rules")
    finally:
        server.shutdown()

    assert response.status == 200
    assert response.payload["read_only"] is False
    assert response.payload["enabled_rule_packs"] == ["python-maintainability"]
    assert rules.payload["enabled_rule_packs"] == ["python-maintainability"]
    assert source_path.read_text() == before_source
    assert (
        'rule_packs = ["python-maintainability"]'
        in (repo / ".codescent" / "config.toml").read_text()
    )


def test_dashboard_rule_update_preserves_existing_config_sections(
    tmp_path: Path,
) -> None:
    repo = _repo_with_finding(tmp_path)
    _ = CodeHealthService(repo).scan()
    config_path = repo / ".codescent" / "config.toml"
    _ = config_path.write_text(
        f"""include = ["src"]
rule_packs = ["python-maintainability", "ts-react-next"]

[project]
schema_version = {SCHEMA_VERSION}

[commands]
test = ["pytest"]
lint = ["ruff check ."]

[token_budgets]
context = 4500
file = 600
dashboard = 12000

[privacy]
runtime_network = false
allow_llm_review = true

[llm]
provider = "openai"
model = "gpt-5.4"
""",
    )

    server = start_dashboard_server(repo, port=0)
    try:
        response = post_json(
            f"{server.base_url}/api/rules",
            {"enabled_rule_packs": ["python-maintainability"]},
        )
        rules = get_json(f"{server.base_url}/api/rules")
    finally:
        server.shutdown()

    config_text = config_path.read_text()
    assert response.status == 200
    assert rules.payload["enabled_rule_packs"] == ["python-maintainability"]
    assert "[project]" in config_text
    assert f"schema_version = {SCHEMA_VERSION}" in config_text
    assert "[commands]" in config_text
    assert 'test = ["pytest"]' in config_text
    assert "[token_budgets]" in config_text
    assert "context = 4500" in config_text
    assert "[privacy]" in config_text
    assert "allow_llm_review = true" in config_text
    assert "[llm]" in config_text
    assert 'model = "gpt-5.4"' in config_text


def test_dashboard_rejects_invalid_rule_config_without_corrupting_config(
    tmp_path: Path,
) -> None:
    repo = _repo_with_finding(tmp_path)
    _ = CodeHealthService(repo).scan()
    config_path = repo / ".codescent" / "config.toml"
    before_config = config_path.read_text()

    server = start_dashboard_server(repo, port=0)
    try:
        unknown = post_json(
            f"{server.base_url}/api/rules",
            {"enabled_rule_packs": ["not-a-pack"]},
        )
        malformed = post_json(
            f"{server.base_url}/api/rules",
            {"enabled_rule_packs": ['bad"pack']},
        )
        rules = get_json(f"{server.base_url}/api/rules")
    finally:
        server.shutdown()

    assert unknown.status == 400
    assert malformed.status == 400
    assert unknown.payload["error"] == "invalid_rule_packs"
    assert malformed.payload["error"] == "invalid_rule_packs"
    assert config_path.read_text() == before_config
    enabled_rule_packs = rules.payload["enabled_rule_packs"]
    assert isinstance(enabled_rule_packs, list)
    assert "python-maintainability" in enabled_rule_packs


def test_dashboard_static_assets_reject_path_traversal(tmp_path: Path) -> None:
    repo = _repo_with_finding(tmp_path)
    _ = CodeHealthService(repo).scan()

    server = start_dashboard_server(repo, port=0)
    try:
        response = get_text(
            f"{server.base_url}/static/../../../../pyproject.toml",
        )
    finally:
        server.shutdown()

    assert response.status == 404
    assert "[project]" not in response.body


def test_dashboard_ui_renders_findings_trends_rules_and_exports(
    tmp_path: Path,
) -> None:
    repo = _repo_with_finding(tmp_path)
    _ = CodeHealthService(repo).scan()

    server = start_dashboard_server(repo, port=0)
    try:
        page = get_text(f"{server.base_url}/")
        css = get_text(f"{server.base_url}/static/dashboard.css")
        script = get_text(f"{server.base_url}/static/dashboard.js")
    finally:
        server.shutdown()

    combined = f"{page.body}\n{css.body}\n{script.body}".lower()
    assert page.status == 200
    assert page.content_type.startswith("text/html")
    assert "findings list" in combined
    assert "selected finding detail" in combined
    assert "progress trend" in combined
    assert "rule config" in combined
    assert "export control" in combined
    assert "marketing" not in combined
    assert "https://" not in combined
    assert "http://" not in combined


def _int_field(payload: JsonObject, key: str) -> int:
    value = payload[key]
    if not isinstance(value, int):
        raise TypeError(value)
    return value


def _repo_with_finding(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """STATUS = "pending-review"
OTHER_STATUS = "pending-review"
THIRD_STATUS = "pending-review"


def load_config() -> str:
    return STATUS
""",
    )
    return repo
