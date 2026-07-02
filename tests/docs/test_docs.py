import re
from pathlib import Path

from typer.testing import CliRunner

from codescent.cli.main import app
from codescent.core.public_surface import (
    LOCKED_POST_MVP_MCP_TOOL_NAMES,
    PUBLIC_SURFACE,
    REGISTERED_MCP_TOOL_NAMES,
)

README = Path("README.md")
CHANGELOG = Path("CHANGELOG.md")
EVALS = Path("docs/evals.md")
MCP_TOOLS = Path("docs/mcp-tools.md")
AGENT_ROUTING = Path("docs/agent-routing.md")
GETTING_STARTED = Path("docs/getting-started.md")
CLI_REFERENCE = Path("docs/cli-reference.md")
WORKFLOWS = Path("docs/workflows.md")
CONFIGURATION = Path("docs/configuration.md")
DASHBOARD = Path("docs/dashboard.md")
LANGUAGE_PACKS = Path("docs/language-packs.md")
AGENTS_TEMPLATE = Path("templates/AGENTS.md")
CLAUDE_TEMPLATE = Path("templates/CLAUDE.md")
CODEX_TEMPLATE = Path("templates/CODEX.md")

DOC_MAP_TARGETS = (
    GETTING_STARTED,
    CLI_REFERENCE,
    MCP_TOOLS,
    WORKFLOWS,
    CONFIGURATION,
    DASHBOARD,
    LANGUAGE_PACKS,
    EVALS,
    AGENT_ROUTING,
    CHANGELOG,
)

DOC_CONTRACT_PATHS = (
    README,
    GETTING_STARTED,
    CLI_REFERENCE,
    MCP_TOOLS,
    WORKFLOWS,
    CONFIGURATION,
    DASHBOARD,
    LANGUAGE_PACKS,
    EVALS,
    AGENT_ROUTING,
    Path("scripts/run_agent_eval.md"),
    Path("evals/agent_task.md"),
)

MVP_TOOLS = {
    "get_repo_map",
    "get_repo_status",
    "search_files",
    "search_content",
    "find_symbol",
    "get_file_context",
    "get_symbol_context",
    "scan_code_health",
    "list_findings",
    "get_next_improvement",
    "plan_refactor",
    "suggest_tests",
    "mark_finding",
    "rescan",
}

POST_MVP_PHRASES = {
    "typescript support",
    "react support",
    "source autofix",
}

POST_MVP_ABSENT_TOOLS = {
    "project_guidance",
    "project_learnings",
    "compress_generic_output",
    "retrieve_original_output",
}


def test_readme_names_python_first_mvp_and_safety() -> None:
    text = README.read_text().lower()

    assert "python-first mvp" in text
    assert "uv sync" in text
    assert "uv run codescent --help" in text
    assert "uv run codescent serve" in text
    assert "uv run codescent serve --repo" not in text
    assert "local stdio" in text
    assert "writes only .codescent" in text
    assert "does not edit analyzed source files" in text
    assert "runtime no-network" in text
    assert "evals/run_deterministic.py" in text
    assert "/users/robertguss/projects/wts-lx/lx_data_lake" in text
    for phrase in POST_MVP_PHRASES:
        assert phrase not in text


def test_no_docs_or_runbooks_use_unsupported_serve_repo_option() -> None:
    combined = "\n".join(
        path.read_text().lower() for path in DOC_CONTRACT_PATHS if path.exists()
    )

    assert "serve --repo" not in combined
    assert "codescent serve --repo" not in combined


def test_original_docs_name_python_first_supersession() -> None:
    combined = "\n".join(
        (
            Path("docs/prd.md").read_text(),
            Path("docs/architecture.md").read_text(),
        ),
    ).lower()

    assert "python-first mvp supersession" in combined
    assert "typescript/javascript/react starting point" in combined
    assert "superseded" in combined


def test_tool_docs_keep_mvp_tools_and_stage_post_mvp_surface() -> None:
    text = MCP_TOOLS.read_text()
    tools = {
        line.removeprefix("- `").removesuffix("`")
        for line in text.splitlines()
        if line.startswith("- `")
    }

    assert tools >= MVP_TOOLS
    assert "registered post-mvp mcp tools" in text.lower()
    assert "locked post-mvp mcp tools" in text.lower()


def test_tool_docs_include_locked_headroom_placeholders() -> None:
    text = MCP_TOOLS.read_text().lower()

    for tool_name in LOCKED_POST_MVP_MCP_TOOL_NAMES:
        assert f"`{tool_name}`" in text
        assert f"- `{tool_name}` - stage `post_mvp`, registered `false`" in text
    assert "task 14" in text


def test_eval_docs_include_deterministic_agent_and_real_smoke() -> None:
    text = EVALS.read_text().lower()

    assert "deterministic offline eval" in text
    assert "agent-in-the-loop eval" in text
    assert "uv run python evals/run_deterministic.py" in text
    assert "scripts/smoke_lx_data_lake.py" in text
    assert "source-read-only" in text


def test_agent_routing_templates_are_documented_and_not_auto_written(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    result = CliRunner().invoke(app, ["doctor", "--repo", str(repo), "--json"])
    combined = (
        f"{AGENT_ROUTING.read_text()}\n"
        f"{AGENTS_TEMPLATE.read_text()}\n"
        f"{CLAUDE_TEMPLATE.read_text()}\n"
        f"{CODEX_TEMPLATE.read_text()}"
    ).lower()

    assert result.exit_code == 0
    assert "routing_templates" in result.output
    assert "use codescent before broad grep" in combined
    assert "source-read-only" in combined
    assert "does not auto-write" in combined
    assert not (repo / "AGENTS.md").exists()
    assert not (repo / "CLAUDE.md").exists()
    assert not (repo / "CODEX.md").exists()


def test_documentation_map_links_exist() -> None:
    text = README.read_text()
    linked_targets = _linked_markdown_targets(text)

    for target in DOC_MAP_TARGETS:
        assert _display_path(target) in text
        assert target in linked_targets
        assert target.exists()

    for path in DOC_CONTRACT_PATHS:
        if path.exists():
            for target in _linked_markdown_targets(path.read_text()):
                assert _resolve_local_markdown_target(path, target).exists()


def test_changelog_has_unreleased_and_initial_release() -> None:
    text = CHANGELOG.read_text()

    assert "## [Unreleased]" in text
    assert "## [0.1.0] - 2026-06-12" in text
    assert "Python-first" in text
    assert "TypeScript/React/Next" in text
    assert "loopback dashboard" in text
    assert "source-read-only" in text
    for future_tool in (
        "retrieve_result",
        "context_stats",
        "project_guidance",
        "project_learnings",
    ):
        assert future_tool not in text


def test_cli_reference_covers_registered_commands() -> None:
    # Collapse whitespace so prose-wrap (prettier proseWrap: "always") cannot
    # split an asserted guidance phrase across a line break.
    text = _collapse_whitespace(CLI_REFERENCE.read_text())
    registered_commands = {
        command.name for command in PUBLIC_SURFACE.cli_commands if command.registered
    }

    for command in registered_commands:
        assert f"`{command}`" in text
    assert "serve --repo" not in text
    assert "codescent dashboard" not in text
    assert "reset requires --dry-run or --yes" in text


def test_mcp_reference_covers_registered_tools() -> None:
    text = MCP_TOOLS.read_text()

    for tool_name in REGISTERED_MCP_TOOL_NAMES:
        section = f"### `{tool_name}`"
        assert section in text
        assert f"`{tool_name}`" in text
        after_section = text.split(section, maxsplit=1)[1]
        section_body = after_section.split("\n### `", maxsplit=1)[0]
        for phrase in (
            "- Group:",
            "- Purpose:",
            "- Inputs:",
            "- Outputs:",
            "- Bounds:",
            "- Example shape:",
        ):
            assert phrase in section_body
    for phrase in (
        "source-read-only",
        "bounded output",
        "Inputs",
        "Outputs",
    ):
        assert phrase in text


def test_mcp_reference_documents_result_retrieval_and_envelopes() -> None:
    text = MCP_TOOLS.read_text().lower()
    find_symbol_section = text.split("### `find_symbol`", maxsplit=1)[1].split(
        "\n### `get_file_context`",
        maxsplit=1,
    )[0]
    retrieve_result_section = text.split("### `retrieve_result`", maxsplit=1)[1].split(
        "\n### `context_stats`",
        maxsplit=1,
    )[0]
    context_stats_section = text.split("### `context_stats`", maxsplit=1)[1].split(
        "\n## Reference Pattern",
        maxsplit=1,
    )[0]

    assert "symbol-search" in find_symbol_section
    assert "envelope" in find_symbol_section
    assert "original_result_id" in find_symbol_section
    assert "retrieval_available" in find_symbol_section
    assert "retrieval_hints" in find_symbol_section
    assert "summarized" in retrieve_result_section
    assert "filtered" in retrieve_result_section
    assert "sample" in retrieve_result_section
    assert "filters only inspect stored json" in retrieve_result_section
    assert "sanitized" in context_stats_section
    assert "session events only" in context_stats_section
    assert "no raw source" in context_stats_section
    assert "raw results" in context_stats_section
    assert "full query payloads" in context_stats_section


def test_mcp_docs_do_not_name_post_mvp_excluded_tools() -> None:
    text = MCP_TOOLS.read_text().lower()

    for tool_name in POST_MVP_ABSENT_TOOLS:
        assert f"`{tool_name}`" not in text


def test_dashboard_docs_do_not_invent_public_command() -> None:
    # Collapse whitespace so prose-wrap cannot split an asserted phrase
    # (e.g. "no remote dashboard") across a line break.
    text = _collapse_whitespace(DASHBOARD.read_text())

    assert "127.0.0.1" in text
    assert "loopback" in text
    assert "no auth" in text
    assert "no remote dashboard" in text
    assert "codescent dashboard" not in text


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _linked_markdown_targets(text: str) -> set[Path]:
    targets: set[Path] = set()
    for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text):
        raw_target = match.group(1)
        if _is_local_markdown_target(raw_target):
            targets.add(Path(raw_target.split("#", maxsplit=1)[0]))
    return targets


def _is_local_markdown_target(raw_target: str) -> bool:
    return (
        not raw_target.startswith(("http://", "https://", "mailto:"))
        and not raw_target.startswith("#")
        and raw_target.split("#", maxsplit=1)[0].endswith(".md")
    )


def _display_path(path: Path) -> str:
    return path.as_posix()


def _resolve_local_markdown_target(source: Path, target: Path) -> Path:
    if target.parts[:1] in (("docs",), ("scripts",), ("evals",)) or target == CHANGELOG:
        return target
    return source.parent / target
