from __future__ import annotations

import json
from dataclasses import dataclass
from http.client import HTTPConnection
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from pydantic import TypeAdapter

from codescent.dashboard.server import start_dashboard_server
from codescent.services.code_health import CodeHealthService

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class HttpJsonResponse:
    status: int
    content_type: str
    payload: dict[str, object]


JSON_OBJECT = TypeAdapter(dict[str, object])


def test_dashboard_binds_loopback_and_serves_local_read_api(tmp_path: Path) -> None:
    repo = _repo_with_finding(tmp_path)
    _ = CodeHealthService(repo).scan()

    server = start_dashboard_server(repo, port=0)
    try:
        assert server.host == "127.0.0.1"
        status = _get_json(f"{server.base_url}/api/status")
        findings = _get_json(f"{server.base_url}/api/findings")
        progress = _get_json(f"{server.base_url}/api/progress")
        rules = _get_json(f"{server.base_url}/api/rules")
        report = _get_json(f"{server.base_url}/api/reports")
        export = _get_json(f"{server.base_url}/api/exports")
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


def _get_json(url: str) -> HttpJsonResponse:
    parsed = urlparse(url)
    connection = HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port or 80)
    try:
        connection.request(
            "GET",
            parsed.path,
            headers={"Accept": "application/json"},
        )
        response = connection.getresponse()
        body = response.read().decode()
        payload = JSON_OBJECT.validate_python(json.loads(body))
        return HttpJsonResponse(
            status=response.status,
            content_type=response.headers.get("content-type", ""),
            payload=payload,
        )
    finally:
        connection.close()


def _int_field(payload: dict[str, object], key: str) -> int:
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
