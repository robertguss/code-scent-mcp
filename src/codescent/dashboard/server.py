from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import urlparse

from codescent.services.findings import FindingsService
from codescent.services.rules import RulesService
from codescent.services.status import RepoStatusService

if TYPE_CHECKING:
    from pathlib import Path


JsonObject = dict[str, object]


@dataclass(frozen=True, slots=True)
class DashboardServer:
    host: str
    port: int
    base_url: str
    _httpd: DashboardHttpServer
    _thread: threading.Thread

    def shutdown(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)


class DashboardHttpServer(ThreadingHTTPServer):
    dashboard: DashboardApplication | None = None


@dataclass(frozen=True, slots=True)
class DashboardApplication:
    repo_root: Path | str
    bind_host: str

    def route(self, path: str) -> tuple[HTTPStatus, JsonObject]:
        route_payloads = {
            "/api/status": self.status,
            "/api/findings": self.findings,
            "/api/progress": self.progress,
            "/api/rules": self.rules,
            "/api/reports": self.report,
            "/api/exports": self.export,
        }
        payload_factory = route_payloads.get(path)
        if payload_factory is None:
            return HTTPStatus.NOT_FOUND, {"error": "not_found", "read_only": True}
        return HTTPStatus.OK, payload_factory()

    def status(self) -> JsonObject:
        status = RepoStatusService(self.repo_root).get_status()
        return {
            "read_only": True,
            "bind_host": self.bind_host,
            "index_fresh": status.index_fresh,
            "indexed_files": status.indexed_files,
            "changed_files": list(status.changed_files),
            "finding_count": status.finding_count,
            "database_ok": status.database_ok,
            "git_available": status.git_available,
            "git_status": status.git_status,
        }

    def findings(self) -> JsonObject:
        rows = FindingsService(self.repo_root).get_smell_report().findings
        return {
            "read_only": True,
            "findings": [
                {
                    "finding_id": row.id,
                    "rule_id": row.rule_id,
                    "file_path": row.file_path,
                    "severity": row.severity,
                    "confidence": row.confidence,
                    "status": row.status.value,
                    "suggested_action": row.suggested_action,
                }
                for row in rows
            ],
        }

    def progress(self) -> JsonObject:
        progress = FindingsService(self.repo_root).get_progress()
        return {
            "read_only": True,
            "total_findings": progress.total_findings,
            "open_count": progress.open_count,
            "resolved_count": progress.resolved_count,
            "regressed_count": progress.regressed_count,
            "status_counts": progress.status_counts,
        }

    def rules(self) -> JsonObject:
        rules = RulesService(self.repo_root).get_rules()
        return {
            "read_only": True,
            "enabled_rule_packs": list(rules.enabled_rule_packs),
            "disabled_rule_packs": list(rules.disabled_rule_packs),
        }

    def report(self) -> JsonObject:
        report = FindingsService(self.repo_root).get_smell_report()
        return {
            "read_only": True,
            "open_count": report.open_count,
            "status_counts": report.status_counts,
            "finding_count": len(report.findings),
        }

    def export(self) -> JsonObject:
        return {
            "read_only": True,
            "format": "json",
            "routes": [
                "/api/status",
                "/api/findings",
                "/api/progress",
                "/api/rules",
                "/api/reports",
                "/api/exports",
            ],
        }


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server_version: str = "CodeScentDashboard/0.1"
    protocol_version: str = "HTTP/1.1"
    _JSON_HEADERS: ClassVar[dict[str, str]] = {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "no-store",
    }

    def do_GET(self) -> None:
        http_server = self.server
        if not isinstance(http_server, DashboardHttpServer):
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if http_server.dashboard is None:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        parsed = urlparse(self.path)
        status, payload = http_server.dashboard.route(parsed.path)
        self._send_json(status, payload)

    def _send_json(self, status: HTTPStatus, payload: JsonObject) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status.value)
        for key, value in self._JSON_HEADERS.items():
            self.send_header(key, value)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        _ = self.wfile.write(body)


def start_dashboard_server(
    repo_root: Path | str,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> DashboardServer:
    application = DashboardApplication(repo_root=repo_root, bind_host=host)
    httpd = DashboardHttpServer((host, port), DashboardRequestHandler)
    httpd.dashboard = application
    bound_port = int(httpd.server_address[1])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return DashboardServer(
        host=host,
        port=bound_port,
        base_url=f"http://{host}:{bound_port}",
        _httpd=httpd,
        _thread=thread,
    )
