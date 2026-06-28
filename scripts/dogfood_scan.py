"""Dogfood gate: run CodeScent's own engine over src/codescent (plan unit U9).

The gate fails CI when a NEW warning-or-higher finding appears on this repo's
own source that is not in the reviewed allowlist (scripts/dogfood_allowlist.json).
info-level heuristics (relative-size outliers, missing-nearby-test for the tests/
layout, dead-code candidates, duplicate literals) are tracked by the engine but
intentionally NOT gated -- see docs/workflows.md.

Examples:
    # Gate: exit 1 if any non-allowlisted warning+ finding appears
    uv run python scripts/dogfood_scan.py

    # Re-record the baseline after an intentional, reviewed change
    uv run python scripts/dogfood_scan.py --update-baseline
"""

from __future__ import annotations

import json
import logging
import socket
import sys
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Final, NoReturn, cast

import typer
from pydantic import TypeAdapter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codescent.engine.packs import build_pack_registry
from codescent.services.config import ConfigService
from codescent.smoke.lx_data_lake_contract import JsonValue

if TYPE_CHECKING:
    from collections.abc import Callable

    from codescent.engine.rules.model import CodeHealthFinding

_REPO_ROOT: Final = Path(__file__).resolve().parents[1]
_DEFAULT_ALLOWLIST: Final = _REPO_ROOT / "scripts" / "dogfood_allowlist.json"
_DEFAULT_OUT: Final = _REPO_ROOT / ".codescent" / "dogfood-scan.json"
_SCOPE: Final = "src/codescent"
_INFO_SEVERITY: Final = "info"
_GATED_MIN_SEVERITY: Final = "warning"

_ALLOWLIST_ADAPTER: Final = TypeAdapter(dict[str, JsonValue])
_DEFAULT_REASONS: Final[dict[str, str]] = {
    "python.large_file": (
        "Module exceeds the absolute line threshold. Reviewed: cohesive module; "
        "splitting now churns imports without cutting complexity. Baseline."
    ),
    "python.large_function": (
        "Function exceeds the absolute line threshold. Reviewed: mostly flat "
        "orchestration/registration/formatting. Baseline."
    ),
    "python.large_class": (
        "Class exceeds the absolute size threshold. Reviewed: cohesive service "
        "surface. Baseline."
    ),
    "python.deep_nesting": (
        "Localized deep nesting. Reviewed: readable as-is. Baseline."
    ),
}

logger = logging.getLogger("codescent.dogfood")


def dogfood_scan(
    repo: Path,
    allowlist_path: Path,
    out: Path | None = None,
) -> dict[str, JsonValue]:
    """Scan src/codescent and assert no non-allowlisted warning+ findings.

    Source is read-only and no network is touched (both asserted in the payload).
    """
    attempts: list[str] = []
    original_socket = socket.socket
    socket.socket = cast("type[socket.socket]", _blocked_socket(attempts))
    try:
        findings = _scan_findings(repo)
    finally:
        socket.socket = original_socket

    gated = [finding for finding in findings if finding.severity != _INFO_SEVERITY]
    allow_keys = _load_allowlist_keys(allowlist_path)
    violations = compute_violations(gated, allow_keys)
    gated_keys = {finding.stable_key for finding in gated}
    stale = sorted(key for key in allow_keys if key not in gated_keys)
    network_attempts = len(attempts)

    _log_report(gated, allow_keys, violations, stale, findings)

    payload: dict[str, JsonValue] = {
        "ok": not violations and network_attempts == 0,
        "repo": _display_repo(repo),
        "scope": _SCOPE,
        "gated_min_severity": _GATED_MIN_SEVERITY,
        "total_findings": len(findings),
        "gated_findings": len(gated),
        "allowlisted": len(allow_keys),
        "violation_count": len(violations),
        "violations": [_finding_payload(finding) for finding in violations],
        "stale_allowlist": list(stale),
        "severity_breakdown": _counter_payload(
            Counter(finding.severity for finding in findings),
        ),
        "rule_breakdown": _counter_payload(
            Counter(finding.rule_id for finding in findings),
        ),
        "network_attempts": network_attempts,
    }
    if out is not None:
        _write_json(out, payload)
    return payload


def compute_violations(
    gated: list[CodeHealthFinding],
    allow_keys: set[str],
) -> list[CodeHealthFinding]:
    """Return gated findings whose stable_key is not in the reviewed allowlist."""
    return sorted(
        (finding for finding in gated if finding.stable_key not in allow_keys),
        key=lambda finding: (finding.file_path, finding.rule_id, finding.symbol or ""),
    )


def update_baseline(repo: Path, allowlist_path: Path) -> int:
    """Rewrite the allowlist from the current gated scan. Returns entry count."""
    findings = _scan_findings(repo)
    gated = sorted(
        (finding for finding in findings if finding.severity != _INFO_SEVERITY),
        key=lambda finding: (
            _finding_path(finding),
            finding.rule_id,
            finding.symbol or "",
            finding.stable_key,
        ),
    )
    reasons = _existing_reasons(allowlist_path)
    entries: dict[str, JsonValue] = {
        finding.stable_key: {
            "rule_id": finding.rule_id,
            "severity": finding.severity,
            "file": _finding_path(finding),
            "symbol": finding.symbol,
        }
        for finding in gated
    }
    doc: dict[str, JsonValue] = {
        "_comment": _existing_comment(allowlist_path),
        "gated_min_severity": _GATED_MIN_SEVERITY,
        "reasons": dict(reasons),
        "findings": entries,
    }
    _ = allowlist_path.write_text(json.dumps(doc, indent=2) + "\n")
    return len(entries)


def _scan_findings(repo: Path) -> tuple[CodeHealthFinding, ...]:
    config = ConfigService(repo).load()
    registry = build_pack_registry(config)
    return registry.scan_rule_packs(repo / _SCOPE)


def _load_allowlist_keys(allowlist_path: Path) -> set[str]:
    if not allowlist_path.exists():
        return set()
    doc = _ALLOWLIST_ADAPTER.validate_json(allowlist_path.read_text())
    findings = doc.get("findings")
    if not isinstance(findings, dict):
        return set()
    return set(findings.keys())


def _existing_reasons(allowlist_path: Path) -> dict[str, str]:
    if not allowlist_path.exists():
        return dict(_DEFAULT_REASONS)
    doc = _ALLOWLIST_ADAPTER.validate_json(allowlist_path.read_text())
    reasons = doc.get("reasons")
    if not isinstance(reasons, dict):
        return dict(_DEFAULT_REASONS)
    return {key: value for key, value in reasons.items() if isinstance(value, str)}


def _existing_comment(allowlist_path: Path) -> str:
    if not allowlist_path.exists():
        return "Reviewed dogfood baseline (plan unit U9)."
    doc = _ALLOWLIST_ADAPTER.validate_json(allowlist_path.read_text())
    comment = doc.get("_comment")
    return comment if isinstance(comment, str) else "Reviewed dogfood baseline."


def _blocked_socket(attempts: list[str]) -> Callable[..., NoReturn]:
    def blocked(*args: object, **kwargs: object) -> NoReturn:
        _ = args, kwargs
        attempts.append("socket")
        message = "network disabled"
        raise AssertionError(message)

    return blocked


def _log_report(
    gated: list[CodeHealthFinding],
    allow_keys: set[str],
    violations: list[CodeHealthFinding],
    stale: list[str],
    findings: tuple[CodeHealthFinding, ...],
) -> None:
    info_count = sum(1 for finding in findings if finding.severity == _INFO_SEVERITY)
    logger.info("Dogfood scan of %s", _SCOPE)
    logger.info(
        "  %d findings total | %d gated (>= %s) | %d info (tracked, not gated)",
        len(findings),
        len(gated),
        _GATED_MIN_SEVERITY,
        info_count,
    )
    for finding in sorted(
        gated,
        key=lambda item: (item.file_path, item.rule_id, item.symbol or ""),
    ):
        verdict = "ALLOW" if finding.stable_key in allow_keys else "NEW  "
        logger.info(
            "  [%s] %-8s %s %s (%s)",
            verdict,
            finding.severity,
            finding.rule_id,
            _finding_path(finding),
            finding.symbol or "-",
        )
    for key in stale:
        logger.info("  [STALE] allowlisted finding no longer present: %s", key)
    if violations:
        logger.error(
            "DOGFOOD GATE FAILED: %d non-allowlisted finding(s)",
            len(violations),
        )
    else:
        logger.info("DOGFOOD GATE PASSED: no non-allowlisted findings")


def _finding_payload(finding: CodeHealthFinding) -> dict[str, JsonValue]:
    return {
        "stable_key": finding.stable_key,
        "rule_id": finding.rule_id,
        "severity": finding.severity,
        "file": _finding_path(finding),
        "symbol": finding.symbol,
        "title": finding.title,
    }


def _finding_path(finding: CodeHealthFinding) -> str:
    return f"{_SCOPE}/{finding.file_path}"


def _counter_payload(counter: Counter[str]) -> dict[str, JsonValue]:
    return {key: counter[key] for key in sorted(counter)}


def _write_json(out: Path, payload: dict[str, JsonValue]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    _ = out.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _display_repo(repo: Path) -> str:
    try:
        return repo.resolve().relative_to(Path.cwd()).as_posix() or "."
    except ValueError:
        return repo.name


def main(
    *,
    repo: Annotated[Path, typer.Option()] = _REPO_ROOT,
    allowlist: Annotated[Path, typer.Option()] = _DEFAULT_ALLOWLIST,
    out: Annotated[Path, typer.Option()] = _DEFAULT_OUT,
    update_baseline_flag: Annotated[
        bool,
        typer.Option("--update-baseline"),
    ] = False,
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if update_baseline_flag:
        count = update_baseline(repo, allowlist)
        typer.echo(json.dumps({"updated_allowlist_entries": count}))
        return
    payload = dogfood_scan(repo, allowlist, out)
    typer.echo(
        json.dumps(
            {"ok": payload["ok"], "violation_count": payload["violation_count"]},
        ),
    )
    if not payload["ok"]:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)
