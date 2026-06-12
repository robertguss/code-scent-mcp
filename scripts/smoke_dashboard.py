from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from codescent.dashboard.server import DashboardServer, start_dashboard_server
from codescent.services.code_health import CodeHealthService

STATUS_OK = 200


@dataclass(frozen=True, slots=True)
class SmokePaths:
    out: Path
    screenshot: Path
    export_json: Path
    export_markdown: Path


def main() -> None:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--repo", required=True)
    _ = parser.add_argument("--out", required=True)
    args = parser.parse_args()
    repo = Path(str(args.repo)).resolve()
    out = Path(str(args.out)).resolve()
    paths = _smoke_paths(out)

    before = _source_hashes(repo)
    server: DashboardServer | None = None
    cleanup = {"server_stopped": False, "chrome_profile_removed": False}
    try:
        _ = CodeHealthService(repo).scan()
        server = start_dashboard_server(repo, port=0)
        page = _get(server.port, "/")
        status = _get(server.port, "/api/status")
        export_payload = _get(server.port, "/api/exports")
        _capture_screenshot(server.base_url, paths.screenshot)
        paths.export_json.write_text(export_payload)
        paths.export_markdown.write_text(_markdown_export(status))
    finally:
        if server is not None:
            server.shutdown()
            cleanup["server_stopped"] = True
        cleanup["chrome_profile_removed"] = _remove_chrome_profiles()

    after = _source_hashes(repo)
    changed_source_paths = [
        path for path, digest in before.items() if after.get(path) != digest
    ]
    created_source_paths = [path for path in after if path not in before]
    payload = {
        "ok": (
            page.startswith("<!doctype html>")
            and paths.screenshot.is_file()
            and not changed_source_paths
            and not created_source_paths
        ),
        "external_requests": _external_request_count(),
        "changed_source_paths": [*changed_source_paths, *created_source_paths],
        "screenshot_path": str(paths.screenshot),
        "exports": {
            "json": str(paths.export_json),
            "markdown": str(paths.export_markdown),
        },
        "cleanup": cleanup,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _smoke_paths(out: Path) -> SmokePaths:
    stem = out.with_suffix("")
    return SmokePaths(
        out=out,
        screenshot=stem.with_name(f"{stem.name}-dashboard.png"),
        export_json=stem.with_name(f"{stem.name}-export.json"),
        export_markdown=stem.with_name(f"{stem.name}-export.md"),
    )


def _source_hashes(repo: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(repo.rglob("*")):
        if (
            path.is_file()
            and ".codescent" not in path.parts
            and "__pycache__" not in path.parts
        ):
            hashes[str(path.relative_to(repo))] = hashlib.sha256(
                path.read_bytes(),
            ).hexdigest()
    return hashes


def _get(port: int, path: str) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read().decode()
        if response.status != STATUS_OK:
            raise RuntimeError(body)
        return body
    finally:
        connection.close()


def _capture_screenshot(url: str, screenshot: Path) -> None:
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not chrome.exists():
        message = "Google Chrome is required for dashboard smoke"
        raise RuntimeError(message)
    node = shutil.which("node")
    if node is None:
        message = "Node is required for Chrome DevTools dashboard smoke"
        raise RuntimeError(message)
    profile = Path(tempfile.gettempdir()) / "codescent-smoke-dashboard-chrome-profile"
    shutil.rmtree(profile, ignore_errors=True)
    remote_port = _free_port()
    command = [
        str(chrome),
        "--headless=new",
        "--disable-gpu",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--metrics-recording-only",
        "--no-first-run",
        f"--remote-debugging-port={remote_port}",
        "--window-size=1440,1000",
        f"--user-data-dir={profile}",
        "about:blank",
    ]
    chrome_process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_for_chrome(remote_port)
        env = {
            **os.environ,
            "DASHBOARD_URL": url,
            "SCREENSHOT_PATH": str(screenshot),
            "REMOTE_PORT": str(remote_port),
        }
        completed = subprocess.run(
            [node, "--input-type=module", "-e", _NODE_SCREENSHOT_SCRIPT],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr)
    finally:
        chrome_process.terminate()
        try:
            _ = chrome_process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            chrome_process.kill()
            _ = chrome_process.communicate(timeout=5)


def _markdown_export(status_json: str) -> str:
    parsed = json.loads(status_json)
    if not isinstance(parsed, dict):
        return "# CodeScent Dashboard Export\n"
    return "\n".join(
        (
            "# CodeScent Dashboard Export",
            "",
            f"- Read only: {parsed.get('read_only')}",
            f"- Index fresh: {parsed.get('index_fresh')}",
            f"- Findings: {parsed.get('finding_count')}",
            "",
        ),
    )


def _external_request_count() -> int:
    combined = "\n".join(
        path.read_text()
        for path in (
            Path("src/codescent/dashboard/templates/dashboard.html"),
            Path("src/codescent/dashboard/static/dashboard.css"),
            Path("src/codescent/dashboard/static/dashboard.js"),
        )
    )
    return combined.count("https://") + combined.count("http://")


def _remove_chrome_profiles() -> bool:
    profile = Path(tempfile.gettempdir()) / "codescent-smoke-dashboard-chrome-profile"
    shutil.rmtree(profile, ignore_errors=True)
    return not profile.exists()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_chrome(port: int) -> None:
    for _ in range(30):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
        try:
            connection.request("GET", "/json/list")
            response = connection.getresponse()
            _ = response.read()
            if response.status == STATUS_OK:
                return
        except OSError:
            time.sleep(0.25)
        finally:
            connection.close()
    message = "Chrome DevTools endpoint did not start"
    raise RuntimeError(message)


_NODE_SCREENSHOT_SCRIPT = r"""
import fs from 'node:fs';
const url = process.env.DASHBOARD_URL;
const screenshotPath = process.env.SCREENSHOT_PATH;
const remotePort = process.env.REMOTE_PORT;
const pages = await fetch(
  `http://127.0.0.1:${remotePort}/json/list`,
).then((r) => r.json());
const target = pages.find((page) => page.type === 'page') ?? pages[0];
const ws = new WebSocket(target.webSocketDebuggerUrl);
let id = 0;
const pending = new Map();
ws.addEventListener('message', (event) => {
  const message = JSON.parse(event.data);
  if (message.id && pending.has(message.id)) {
    pending.get(message.id)(message);
    pending.delete(message.id);
  }
});
await new Promise((resolve) => ws.addEventListener('open', resolve, { once: true }));
function send(method, params = {}) {
  const commandId = ++id;
  ws.send(JSON.stringify({ id: commandId, method, params }));
  return new Promise((resolve) => pending.set(commandId, resolve));
}
async function evalValue(expression) {
  const result = await send(
    'Runtime.evaluate',
    { expression, returnByValue: true, awaitPromise: true },
  );
  return result.result.result.value;
}
await send('Page.enable');
await send('Runtime.enable');
await send(
  'Emulation.setDeviceMetricsOverride',
  { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false },
);
await send('Page.navigate', { url });
for (let attempt = 0; attempt < 30; attempt += 1) {
  const ready = await evalValue(
    "document.querySelectorAll('.trend-row').length >= 3"
      + " && document.querySelectorAll('.rule-item').length >= 1",
  );
  if (ready) break;
  await new Promise((resolve) => setTimeout(resolve, 250));
}
const screenshot = await send(
  'Page.captureScreenshot',
  { format: 'png', captureBeyondViewport: false },
);
fs.writeFileSync(screenshotPath, Buffer.from(screenshot.result.data, 'base64'));
ws.close();
"""


if __name__ == "__main__":
    main()
