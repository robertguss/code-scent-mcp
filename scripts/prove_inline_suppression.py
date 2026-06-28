"""E2E proof: an inline `# codescent: ignore[...]` round-trips correctly.

Builds a throwaway repo with two genuinely-dead functions, suppresses one via an
ignore comment, and asserts (with verbose expected-vs-found logging) that:

  * the annotated finding is `suppressed` with an audit trail,
  * the un-annotated finding stays `open`,
  * removing the comment reopens the finding.

No network, source is only read. Writes a JSON receipt to --out.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Annotated

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codescent.core.models import FindingStatus
from codescent.services.code_health import CodeHealthService
from codescent.services.findings import FindingsService

_IGNORE = "# codescent: ignore[python.dead_code_candidate]"
_NEUTRAL = "# placeholder"
_BODY = (
    "def _alpha_dead() -> int:\n"
    "    return 1\n"
    "\n"
    "\n"
    "def _beta_dead() -> int:\n"
    "    return 2\n"
)


def _write(repo: Path, first_line: str) -> None:
    source = repo / "src" / "pkg" / "analysis.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    _ = source.write_text(f"{first_line}\n{_BODY}")


def _statuses(repo: Path) -> dict[str, str]:
    findings = FindingsService(repo).get_smell_report().findings
    return {finding.stable_key: finding.status.value for finding in findings}


def _check(
    checks: list[dict[str, object]], label: str, *, expected: object, found: object
) -> None:
    ok = expected == found
    checks.append({"check": label, "expected": expected, "found": found, "ok": ok})
    typer.echo(
        f"[{'PASS' if ok else 'FAIL'}] {label}: expected={expected!r} found={found!r}"
    )


def prove_inline_suppression(repo: Path, out: Path) -> dict[str, object]:
    shutil.rmtree(repo / ".codescent", ignore_errors=True)
    checks: list[dict[str, object]] = []

    # 1) Suppressed scan: one finding silenced, the other open.
    _write(repo, _IGNORE)
    _ = CodeHealthService(repo).scan()
    findings = FindingsService(repo).get_smell_report().findings
    suppressed = [f for f in findings if f.status is FindingStatus.SUPPRESSED]
    dead_open = [
        f
        for f in findings
        if f.status is FindingStatus.OPEN and f.rule_id == "python.dead_code_candidate"
    ]
    _check(checks, "one finding suppressed", expected=1, found=len(suppressed))
    _check(
        checks, "sibling dead-code finding stays open", expected=1, found=len(dead_open)
    )

    # 2) Audit trail: a `suppressed` event carrying the comment text.
    audit_ok = bool(suppressed) and any(
        event.event_type == "suppressed" and "codescent: ignore" in event.details_json
        for event in suppressed[0].events
    )
    _check(checks, "audit event records the comment", expected=True, found=audit_ok)
    suppressed_key = suppressed[0].stable_key if suppressed else ""

    # 3) Remove the comment -> the finding reappears as open (same key).
    _write(repo, _NEUTRAL)
    _ = CodeHealthService(repo).scan()
    reopened_status = _statuses(repo).get(suppressed_key)
    _check(
        checks,
        "removing the comment reopens the finding",
        expected=FindingStatus.OPEN.value,
        found=reopened_status,
    )

    ok = all(bool(check["ok"]) for check in checks)
    payload: dict[str, object] = {"ok": ok, "repo": repo.name, "checks": checks}
    out.parent.mkdir(parents=True, exist_ok=True)
    _ = out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def main(
    out: Annotated[Path, typer.Option()],
    repo: Annotated[Path | None, typer.Option()] = None,
) -> None:
    if repo is None:
        repo = Path(tempfile.mkdtemp(prefix="codescent-suppression-"))
    payload = prove_inline_suppression(repo, out)
    typer.echo(json.dumps({"ok": payload["ok"]}))
    if not payload["ok"]:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)
