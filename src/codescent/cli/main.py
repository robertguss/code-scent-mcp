from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING, Annotated, NoReturn, TypedDict

import typer

from codescent import __version__
from codescent.core.errors import CodeScentError
from codescent.core.paths import resolve_repo_root
from codescent.mcp.server import mcp_available
from codescent.mcp.server import run as run_mcp
from codescent.services.ci import CiReport, CiService
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService
from codescent.services.findings import FindingsService
from codescent.services.repo_index import RepoIndexService
from codescent.services.reports import ReportService
from codescent.services.rules import RulesService
from codescent.services.status import RepoStatusService
from codescent.services.subjective_review import (
    SubjectiveReviewService,
    subjective_findings_payload,
)
from codescent.storage import initialize_storage

if TYPE_CHECKING:
    from codescent.storage.repositories import FindingRow

INVALID_FORMAT_MESSAGE = "format must be json or markdown"


class CliReportPayload(TypedDict):
    open_count: int
    status_counts: dict[str, int]
    findings: list[dict[str, str | float]]
    subjective_findings: list[dict[str, str | float | bool]]
    subjective_provider: str | None
    privacy_notice: str | None


class CiReportPayload(TypedDict):
    ok: bool
    risk_level: str
    finding_count: int
    changed_file_health: list[dict[str, object]]
    suggested_tests: list[str]
    recommended_commands: list[str]

app = typer.Typer(
    add_completion=False,
    help="Local MCP-first codebase improvement server.",
    no_args_is_help=True,
)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", help="Print the CodeScent version and exit."),
    ] = False,
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit


@app.command()
def init(
    repo: Annotated[
        str,
        typer.Option("--repo", help="Repository root to initialize."),
    ] = ".",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON initialization result."),
    ] = False,
) -> None:
    try:
        state = initialize_storage(repo)
    except CodeScentError as error:
        _exit_with_error(error, json_output=json_output)
    if json_output:
        typer.echo(json.dumps({"state_dir": str(state.state_dir)}))
        return
    typer.echo(f"Initialized CodeScent state at {state.state_dir}")


@app.command()
def index(
    repo: Annotated[
        str,
        typer.Option("--repo", help="Repository root to index."),
    ] = ".",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON index result."),
    ] = False,
) -> None:
    try:
        result = RepoIndexService(repo).index_repo()
    except CodeScentError as error:
        _exit_with_error(error, json_output=json_output)
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "indexed_files": result.indexed_files,
                    "changed_files": list(result.changed_files),
                    "git_available": result.git_available,
                    "git_status": result.git_status,
                },
            ),
        )
        return
    typer.echo(f"Indexed {result.indexed_files} files")


@app.command()
def status(
    repo: Annotated[
        str,
        typer.Option("--repo", help="Repository root to inspect."),
    ] = ".",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON status."),
    ] = False,
) -> None:
    try:
        repo_status = RepoStatusService(repo).get_status()
    except CodeScentError as error:
        _exit_with_error(error, json_output=json_output)
    payload = {
        "index_fresh": repo_status.index_fresh,
        "indexed_files": repo_status.indexed_files,
        "changed_files": list(repo_status.changed_files),
        "finding_count": repo_status.finding_count,
        "database_ok": repo_status.database_ok,
        "git_available": repo_status.git_available,
        "git_status": repo_status.git_status,
    }
    if json_output:
        typer.echo(json.dumps(payload))
        return
    typer.echo(f"Index fresh: {repo_status.index_fresh}")


@app.command()
def scan(
    repo: Annotated[
        str,
        typer.Option("--repo", help="Repository root to scan."),
    ] = ".",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON scan placeholder."),
    ] = False,
) -> None:
    try:
        result = CodeHealthService(repo).scan()
    except CodeScentError as error:
        _exit_with_error(error, json_output=json_output)
    payload = {
        "status": "complete",
        "scan_id": result.scan_id,
        "files_scanned": result.files_scanned,
        "findings_created": result.findings_created,
        "findings_resolved": result.findings_resolved,
        "finding_ids": list(result.finding_ids),
        "rule_ids": list(result.rule_ids),
        "findings": [
            {
                "id": finding.id,
                "stable_key": finding.stable_key,
                "rule_id": finding.rule_id,
                "file_path": finding.file_path,
                "symbol": finding.symbol,
                "severity": finding.severity,
                "confidence": finding.confidence,
                "evidence": finding.evidence,
                "suggested_action": finding.suggested_action,
            }
            for finding in result.findings
        ],
    }
    if json_output:
        typer.echo(json.dumps(payload))
        return
    typer.echo(
        f"Scanned {result.files_scanned} files; {result.findings_created} findings"
    )


@app.command()
def doctor(
    repo: Annotated[
        str,
        typer.Option("--repo", help="Repository root to diagnose."),
    ] = ".",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON diagnostics."),
    ] = False,
) -> None:
    try:
        repo_root = resolve_repo_root(repo)
    except CodeScentError as error:
        _exit_with_error(error, json_output=json_output)
    state_dir = repo_root / ".codescent"
    database_path = state_dir / "index.sqlite"
    config_path = state_dir / "config.toml"
    database_ok = database_path.is_file()
    config_ok = config_path.is_file()
    checks = {
        "database_ok": database_ok,
        "config_ok": config_ok,
        "exclusions_ok": not (state_dir / ".codescent").exists(),
        "mcp_available": mcp_available(),
    }
    payload = {
        "ok": all(checks.values()),
        "checks": checks,
        "warnings": _doctor_warnings(database_ok=database_ok, config_ok=config_ok),
        "routing_templates": _routing_templates(),
    }
    if json_output:
        typer.echo(json.dumps(payload))
        return
    typer.echo("Doctor OK" if payload["ok"] else "Doctor found issues")


@app.command()
def report(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    format_name: Annotated[
        str,
        typer.Option("--format", help="Output format: json or markdown."),
    ] = "json",
    include_subjective: Annotated[
        bool,
        typer.Option("--include-subjective", help="Include opt-in subjective review."),
    ] = False,
    provider: Annotated[
        str,
        typer.Option("--provider", help="Subjective review provider."),
    ] = "fake",
) -> None:
    report_data = FindingsService(repo).get_smell_report()
    subjective = SubjectiveReviewService(repo).review(
        provider_name=provider,
        allow_subjective=include_subjective,
    )
    payload: CliReportPayload = {
        "open_count": report_data.open_count,
        "status_counts": report_data.status_counts,
        "findings": [_finding_row_payload(finding) for finding in report_data.findings],
        "subjective_findings": subjective_findings_payload(
            subjective.subjective_findings,
        ),
        "subjective_provider": subjective.provider,
        "privacy_notice": subjective.privacy_notice,
    }
    _emit_report_payload(payload, format_name)


@app.command()
def export(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    format_name: Annotated[
        str,
        typer.Option("--format", help="Output format: json or markdown."),
    ] = "json",
) -> None:
    report_data = FindingsService(repo).get_smell_report()
    payload: CliReportPayload = {
        "open_count": report_data.open_count,
        "status_counts": report_data.status_counts,
        "findings": [_finding_row_payload(finding) for finding in report_data.findings],
        "subjective_findings": [],
        "subjective_provider": None,
        "privacy_notice": None,
    }
    _emit_report_payload(payload, format_name)


@app.command()
def findings(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON findings."),
    ] = False,
) -> None:
    rows = FindingsService(repo).get_smell_report().findings
    payload = {"findings": [_finding_row_payload(finding) for finding in rows]}
    if json_output:
        typer.echo(json.dumps(payload))
        return
    for finding in payload["findings"]:
        typer.echo(f"{finding['finding_id']} {finding['rule_id']}")


@app.command(name="next")
def next_improvement(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON next improvement."),
    ] = False,
) -> None:
    finding = FindingsService(repo).get_next_improvement()
    payload = None if finding is None else _finding_row_payload(finding)
    if json_output:
        typer.echo(json.dumps({"finding": payload}))
        return
    typer.echo("No findings" if payload is None else payload["finding_id"])


@app.command()
def explain(
    finding_id: str,
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON score explanation."),
    ] = False,
) -> None:
    explanation = ReportService(repo).explain_score(finding_id)
    payload = {
        "finding_id": explanation.finding_id,
        "score_inputs": explanation.score_inputs,
        "reasons": list(explanation.reasons),
        "next_steps": list(explanation.next_steps),
        "subjective": explanation.subjective,
    }
    if json_output:
        typer.echo(json.dumps(payload))
        return
    typer.echo("\n".join(explanation.reasons))


@app.command()
def config(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON project config."),
    ] = False,
) -> None:
    project_config = ConfigService(repo).load()
    payload = project_config.model_dump(mode="json")
    if json_output:
        typer.echo(json.dumps(payload))
        return
    typer.echo(json.dumps(payload, indent=2))


@app.command()
def rules(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON rule configuration."),
    ] = False,
) -> None:
    report_data = RulesService(repo).get_rules()
    payload = {
        "enabled_rule_packs": list(report_data.enabled_rule_packs),
        "disabled_rule_packs": list(report_data.disabled_rule_packs),
    }
    if json_output:
        typer.echo(json.dumps(payload))
        return
    typer.echo("\n".join(payload["enabled_rule_packs"]))


@app.command()
def watch(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    once: Annotated[
        bool,
        typer.Option("--once", help="Run one index pass and exit."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON watch result."),
    ] = False,
) -> None:
    result = RepoIndexService(repo).index_repo()
    payload = {
        "mode": "once" if once else "poll",
        "indexed_files": result.indexed_files,
        "changed_files": list(result.changed_files),
    }
    if json_output:
        typer.echo(json.dumps(payload))
        return
    typer.echo(f"Indexed {result.indexed_files} files")


@app.command()
def reset(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="List reset targets without deleting."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Delete .codescent state."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON reset result."),
    ] = False,
) -> None:
    repo_root = resolve_repo_root(repo)
    target = repo_root / ".codescent"
    paths = [str(target)]
    deleted = False
    if not dry_run:
        if not yes:
            typer.echo("reset requires --dry-run or --yes", err=True)
            raise typer.Exit(1)
        shutil.rmtree(target, ignore_errors=True)
        deleted = True
    payload = {"deleted": deleted, "paths": paths}
    if json_output:
        typer.echo(json.dumps(payload))
        return
    typer.echo(json.dumps(payload))


@app.command()
def ci(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    format_name: Annotated[
        str,
        typer.Option("--format", help="Output format: json or markdown."),
    ] = "json",
    threshold: Annotated[
        str,
        typer.Option("--threshold", help="Fail at risk threshold: warn or high."),
    ] = "high",
) -> None:
    report_data = CiService(repo).run(threshold=threshold)
    _emit_ci_report(report_data, format_name)
    if not report_data.ok:
        raise typer.Exit(1)


@app.command(name="review-diff")
def review_diff(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
    format_name: Annotated[
        str,
        typer.Option("--format", help="Output format: json or markdown."),
    ] = "json",
) -> None:
    report_data = CiService(repo).run(threshold="high")
    _emit_ci_report(report_data, format_name)


@app.command()
def serve() -> None:
    run_mcp()


def _exit_with_error(error: CodeScentError, *, json_output: bool = False) -> NoReturn:
    if json_output:
        typer.echo(json.dumps(error.to_payload()))
    else:
        typer.echo(str(error), err=True)
    raise typer.Exit(1)


def _doctor_warnings(*, database_ok: bool, config_ok: bool) -> list[str]:
    warnings: list[str] = []
    if not database_ok:
        warnings.append("codescent database has not been initialized")
    if not config_ok:
        warnings.append("codescent config has not been initialized")
    return warnings


def _routing_templates() -> list[dict[str, str | bool]]:
    return [
        {
            "name": "AGENTS.md",
            "template": "templates/AGENTS.md",
            "auto_write": False,
        },
        {
            "name": "CLAUDE.md",
            "template": "templates/CLAUDE.md",
            "auto_write": False,
        },
        {
            "name": "CODEX.md",
            "template": "templates/CODEX.md",
            "auto_write": False,
        },
    ]


def _finding_row_payload(finding: FindingRow) -> dict[str, str | float]:
    return {
        "finding_id": finding.id,
        "rule_id": finding.rule_id,
        "file_path": finding.file_path,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "status": finding.status.value,
        "suggested_action": finding.suggested_action,
    }


def _emit_report_payload(payload: CliReportPayload, format_name: str) -> None:
    if format_name == "json":
        typer.echo(json.dumps(payload))
        return
    if format_name == "markdown":
        typer.echo(_markdown_report(payload))
        return
    raise typer.BadParameter(INVALID_FORMAT_MESSAGE)


def _markdown_report(payload: CliReportPayload) -> str:
    lines = ["# CodeScent Report", ""]
    findings = payload["findings"]
    lines.append(f"Findings: {len(findings)}")
    lines.extend(
        f"- {finding['finding_id']}: {finding['rule_id']}"
        for finding in findings
    )
    return "\n".join(lines)


def _emit_ci_report(report_data: CiReport, format_name: str) -> None:
    payload = _ci_payload(report_data)
    if format_name == "json":
        typer.echo(json.dumps(payload))
        return
    if format_name == "markdown":
        typer.echo(_ci_markdown(payload))
        return
    raise typer.BadParameter(INVALID_FORMAT_MESSAGE)


def _ci_payload(report_data: CiReport) -> CiReportPayload:
    return {
        "ok": report_data.ok,
        "risk_level": report_data.risk_level,
        "finding_count": report_data.finding_count,
        "changed_file_health": [
            {
                "path": health.path,
                "risk_level": health.risk_level,
                "risk_score": health.risk_score,
                "finding_count": health.finding_count,
            }
            for health in report_data.changed_file_health
        ],
        "suggested_tests": list(report_data.suggested_tests),
        "recommended_commands": list(report_data.recommended_commands),
    }


def _ci_markdown(payload: CiReportPayload) -> str:
    lines = [
        "# CodeScent Diff Review",
        "",
        f"Risk: {payload['risk_level']}",
        f"Findings: {payload['finding_count']}",
        "",
        "## Changed-file health",
    ]
    lines.extend(
        f"- {item['path']}: {item['risk_level']}"
        for item in payload["changed_file_health"]
    )
    lines.extend(("", "## Suggested tests"))
    lines.extend(f"- {test}" for test in payload["suggested_tests"])
    return "\n".join(lines)
