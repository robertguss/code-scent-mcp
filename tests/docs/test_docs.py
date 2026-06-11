from pathlib import Path

README = Path("README.md")
EVALS = Path("docs/evals.md")
MCP_TOOLS = Path("docs/mcp-tools.md")

MVP_TOOLS = {
    "get_repo_map",
    "get_repo_status",
    "search_files",
    "search_content",
    "find_symbol",
    "get_file_context",
    "get_symbol_context",
    "scan_code_health",
    "get_smell_report",
    "get_finding_context",
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
    paths = [
        README,
        EVALS,
        MCP_TOOLS,
        Path("scripts/run_agent_eval.md"),
        Path("evals/agent_task.md"),
    ]
    combined = "\n".join(path.read_text().lower() for path in paths)

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


def test_eval_docs_include_deterministic_agent_and_real_smoke() -> None:
    text = EVALS.read_text().lower()

    assert "deterministic offline eval" in text
    assert "agent-in-the-loop eval" in text
    assert "uv run python evals/run_deterministic.py" in text
    assert "scripts/smoke_lx_data_lake.py" in text
    assert "source-read-only" in text
