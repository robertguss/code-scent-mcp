import json
from typing import Annotated, NoReturn

import typer

from codescent import __version__
from codescent.core.errors import CodeScentError
from codescent.core.paths import resolve_repo_root
from codescent.mcp.server import mcp_available
from codescent.mcp.server import run as run_mcp
from codescent.services.code_health import CodeHealthService
from codescent.services.repo_index import RepoIndexService
from codescent.services.status import RepoStatusService
from codescent.storage import initialize_storage

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
    }
    if json_output:
        typer.echo(json.dumps(payload))
        return
    typer.echo("Doctor OK" if payload["ok"] else "Doctor found issues")


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
