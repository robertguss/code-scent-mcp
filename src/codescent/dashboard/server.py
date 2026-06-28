from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse

from codescent.dashboard.payloads import (
    DASHBOARD_API_ROUTES,
    JSON_OBJECT,
    JsonObject,
    asset_text,
    json_int_map,
    provenance_object,
    string_list,
)
from codescent.services.findings import FindingsService
from codescent.services.precision import PrecisionService
from codescent.services.rules import RulesService
from codescent.services.status import RepoStatusService


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


class DashboardHttpServer(HTTPServer):
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
            "/api/precision": self.precision,
            "/api/rules": self.rules,
            "/api/reports": self.report,
            "/api/exports": self.export,
        }
        payload_factory = route_payloads.get(path)
        if payload_factory is None:
            return HTTPStatus.NOT_FOUND, {"error": "not_found", "read_only": True}
        return HTTPStatus.OK, payload_factory()

    def post(self, path: str, payload: JsonObject) -> tuple[HTTPStatus, JsonObject]:
        if path != "/api/rules":
            return HTTPStatus.NOT_FOUND, {"error": "not_found", "read_only": True}
        enabled = string_list(payload.get("enabled_rule_packs"))
        if enabled is None:
            return HTTPStatus.BAD_REQUEST, {
                "error": "invalid_rule_packs",
                "read_only": True,
            }
        service = RulesService(self.repo_root)
        enabled_packs = tuple(enabled)
        if not service.is_valid_rule_pack_selection(enabled_packs):
            return HTTPStatus.BAD_REQUEST, {
                "error": "invalid_rule_packs",
                "read_only": True,
            }
        rules = service.update_rules(enabled_packs)
        return HTTPStatus.OK, {
            "read_only": False,
            "enabled_rule_packs": list(rules.enabled_rule_packs),
            "disabled_rule_packs": list(rules.disabled_rule_packs),
        }

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
        precision_by_rule = PrecisionService(
            self.repo_root,
        ).acceptance_precision_by_rule()
        return {
            "read_only": True,
            "findings": [
                {
                    "finding_id": row.id,
                    "rule_id": row.rule_id,
                    "file_path": row.file_path,
                    "severity": row.severity,
                    "confidence": row.confidence,
                    "confidence_tier": row.confidence_tier,
                    "provenance": provenance_object(row.provenance_json),
                    "acceptance_precision": precision_by_rule.get(row.rule_id),
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
            "status_counts": json_int_map(progress.status_counts),
        }

    def precision(self) -> JsonObject:
        report = PrecisionService(self.repo_root).get_precision()
        return {
            "read_only": True,
            "accepted": report.accepted,
            "dismissed": report.dismissed,
            "sample_size": report.sample_size,
            "acceptance_precision": report.acceptance_precision,
            "rules": [
                {
                    "rule_id": rule.rule_id,
                    "accepted": rule.accepted,
                    "dismissed": rule.dismissed,
                    "sample_size": rule.sample_size,
                    "acceptance_precision": rule.acceptance_precision,
                    "suppression_candidates": rule.suppression_candidates,
                }
                for rule in report.rules
            ],
            "trend": [
                {
                    "date": point.date,
                    "accepted": point.accepted,
                    "dismissed": point.dismissed,
                    "acceptance_precision": point.acceptance_precision,
                }
                for point in report.trend
            ],
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
            "status_counts": json_int_map(report.status_counts),
            "finding_count": len(report.findings),
        }

    def export(self) -> JsonObject:
        return {
            "read_only": True,
            "format": "json",
            "routes": list(DASHBOARD_API_ROUTES),
        }


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server_version: str = "CodeScentDashboard/0.1"
    protocol_version: str = "HTTP/1.0"
    _JSON_HEADERS: ClassVar[dict[str, str]] = {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "no-store",
    }
    _TEXT_TYPES: ClassVar[dict[str, str]] = {
        ".css": "text/css; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
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
        if parsed.path == "/":
            self._send_text(HTTPStatus.OK, asset_text("templates/dashboard.html"))
            return
        if parsed.path.startswith("/static/"):
            self._send_static(parsed.path.removeprefix("/static/"))
            return
        status, payload = http_server.dashboard.route(parsed.path)
        self._send_json(status, payload)

    def do_POST(self) -> None:
        http_server = self.server
        if not isinstance(http_server, DashboardHttpServer):
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if http_server.dashboard is None:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        parsed = urlparse(self.path)
        payload = self._read_json_body()
        if payload is None:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_json", "read_only": True},
            )
            return
        status, response = http_server.dashboard.post(parsed.path, payload)
        self._send_json(status, response)

    def _send_json(self, status: HTTPStatus, payload: JsonObject) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status.value)
        for key, value in self._JSON_HEADERS.items():
            self.send_header(key, value)
        self.send_header("connection", "close")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        _ = self.wfile.write(body)

    def _send_text(
        self,
        status: HTTPStatus,
        body: str,
        *,
        content_type: str = "text/html; charset=utf-8",
    ) -> None:
        encoded = body.encode()
        self.send_response(status.value)
        self.send_header("content-type", content_type)
        self.send_header("cache-control", "no-store")
        self.send_header("connection", "close")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        _ = self.wfile.write(encoded)

    def _send_static(self, path: str) -> None:
        asset_path = f"static/{path}"
        suffix = Path(path).suffix
        try:
            body = asset_text(asset_path)
        except FileNotFoundError:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found", "read_only": True},
            )
            return
        self._send_text(
            HTTPStatus.OK,
            body,
            content_type=self._TEXT_TYPES.get(
                suffix,
                "text/plain; charset=utf-8",
            ),
        )

    def _read_json_body(self) -> JsonObject | None:
        content_length = self.headers.get("content-length", "0")
        try:
            length = int(content_length)
            raw = self.rfile.read(length)
            return JSON_OBJECT.validate_json(raw)
        except (ValueError, json.JSONDecodeError):
            return None


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
