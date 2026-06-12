# DASHBOARD GUIDANCE

## OVERVIEW

`src/codescent/dashboard` is a local loopback dashboard served by Python with
bundled HTML, CSS, and JavaScript. It is not a standalone frontend app.

## STRUCTURE

```text
dashboard/
+-- server.py
+-- payloads.py
+-- templates/dashboard.html
+-- static/
    +-- dashboard.css
    +-- dashboard.js
```

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| HTTP server and routes | `server.py` | Local JSON API and static/template serving. |
| Response models | `payloads.py` | Dashboard-specific structured payloads. |
| UI behavior | `static/dashboard.js` | Client-side interactions and fetches. |
| Visual style | `static/dashboard.css` | Plain bundled CSS, no build step. |
| HTML shell | `templates/dashboard.html` | Served by the Python dashboard server. |
| Smoke verification | `scripts/smoke_dashboard.py` | Uses Chrome/Node and temp artifacts. |

## CONVENTIONS

- Keep the dashboard local-only and source-read-only. Config/rule updates may
  write `.codescent/config.toml`, not analyzed source.
- Reject path traversal and keep static/template serving rooted in this package.
- There is no frontend package manager for this UI; edit bundled assets directly.
- Preserve JSON response contracts covered by integration/security tests.

## ANTI-PATTERNS

- Do not add external runtime network dependencies to render or smoke the UI.
- Do not introduce a JS build pipeline unless the repo explicitly adopts one.
- Do not let dashboard export/config actions bypass `.codescent` state limits.
