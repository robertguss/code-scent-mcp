from __future__ import annotations

import json
import shutil
import sys
from typing import Annotated, NoReturn, Protocol, runtime_checkable

import typer

from codescent.core.errors import CodeScentError
from codescent.core.paths import resolve_repo_root
from codescent.services.config import ConfigService
from codescent.services.repo_index import RepoIndexService
from codescent.services.rules import RulesService


@runtime_checkable
class McpAvailableModule(Protocol):
    def mcp_available(self) -> bool: ...


def register_admin_commands(app: typer.Typer) -> None:
    _ = app.command()(doctor)
    _ = app.command()(config)
    _ = app.command()(rules)
    _ = app.command()(watch)
    _ = app.command()(reset)


def doctor(
    repo: Annotated[str, typer.Option("--repo", help="Repository root.")] = ".",
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
    checks = {
        "database_ok": (state_dir / "index.sqlite").is_file(),
        "config_ok": (state_dir / "config.toml").is_file(),
        "exclusions_ok": not (state_dir / ".codescent").exists(),
        "mcp_available": _mcp_available(),
    }
    payload = {
        "ok": all(checks.values()),
        "checks": checks,
        "warnings": _doctor_warnings(
            database_ok=checks["database_ok"],
            config_ok=checks["config_ok"],
        ),
        "routing_templates": _routing_templates(),
    }
    if json_output:
        typer.echo(json.dumps(payload))
        return
    typer.echo("Doctor OK" if payload["ok"] else "Doctor found issues")


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
    deleted = False
    if not dry_run:
        if not yes:
            typer.echo("reset requires --dry-run or --yes", err=True)
            raise typer.Exit(1)
        shutil.rmtree(target, ignore_errors=True)
        deleted = True
    payload = {"deleted": deleted, "paths": [str(target)]}
    if json_output:
        typer.echo(json.dumps(payload))
        return
    typer.echo(json.dumps(payload))


def _exit_with_error(error: CodeScentError, *, json_output: bool = False) -> NoReturn:
    if json_output:
        typer.echo(json.dumps(error.to_payload()))
    else:
        typer.echo(str(error), err=True)
    raise typer.Exit(1)


def _mcp_available() -> bool:
    cli_main = sys.modules["codescent.cli.main"]
    if not isinstance(cli_main, McpAvailableModule):
        return False
    return cli_main.mcp_available()


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
