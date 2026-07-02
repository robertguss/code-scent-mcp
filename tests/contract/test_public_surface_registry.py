from codescent.core.public_surface import (
    ABSENT_MCP_TOOL_NAMES,
    MVP_MCP_TOOL_NAMES,
    POST_MVP_CLI_COMMAND_NAMES,
    POST_MVP_MCP_TOOL_NAMES,
    PUBLIC_SURFACE,
    REGISTERED_MCP_TOOL_NAMES,
    REGISTERED_POST_MVP_MCP_TOOL_NAMES,
    SurfaceStage,
    known_mcp_tool_names,
    registered_mcp_tool_names,
)

# Snapshot of the MVP set the derived-from-PUBLIC_SURFACE frozensets must still
# equal after the F8 collapse (guards against the derivation drifting).
_EXPECTED_MVP = frozenset(
    {
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
    },
)

# The registry's own frozensets are the single source of truth for the split a
# surface merge flips; the guard and this test read them, nothing redefines it.
ABSENT_POST_MVP_MCP_TOOL_NAMES = ABSENT_MCP_TOOL_NAMES


def test_post_mvp_surface_tracks_registered_and_locked_tools() -> None:
    # Given: the public surface registry is the source of truth for docs and tests.
    registered_mvp = {
        entry.name
        for entry in PUBLIC_SURFACE.mcp_tools
        if entry.stage is SurfaceStage.MVP
    }
    declared_post_mvp = {
        entry.name
        for entry in PUBLIC_SURFACE.mcp_tools
        if entry.stage is SurfaceStage.POST_MVP
    }

    # When: a worker needs to expose future tools.
    # Then: MVP runtime tools stay stable while post-MVP tools are declared.
    assert registered_mvp == MVP_MCP_TOOL_NAMES
    assert declared_post_mvp >= POST_MVP_MCP_TOOL_NAMES
    assert {"retrieve_result", "context_stats"} <= declared_post_mvp
    assert {
        entry.name
        for entry in PUBLIC_SURFACE.mcp_tools
        if entry.stage is SurfaceStage.POST_MVP and entry.registered
    } == REGISTERED_POST_MVP_MCP_TOOL_NAMES
    assert (
        sum(1 for entry in PUBLIC_SURFACE.mcp_tools if entry.name == "retrieve_result")
        == 1
    )
    assert (
        sum(1 for entry in PUBLIC_SURFACE.mcp_tools if entry.name == "context_stats")
        == 1
    )
    assert "retrieve_result" in REGISTERED_POST_MVP_MCP_TOOL_NAMES
    assert "context_stats" in REGISTERED_POST_MVP_MCP_TOOL_NAMES
    # Every PUBLIC_SURFACE entry is registered, so there is no locked split.
    assert {
        entry.name
        for entry in PUBLIC_SURFACE.mcp_tools
        if entry.stage is SurfaceStage.POST_MVP and not entry.registered
    } == set()
    assert registered_mvp.isdisjoint(declared_post_mvp)
    assert ABSENT_POST_MVP_MCP_TOOL_NAMES.isdisjoint(
        {entry.name for entry in PUBLIC_SURFACE.mcp_tools}
    )


def test_derived_frozensets_match_the_public_surface_and_snapshot() -> None:
    # F8 collapse: the frozensets are derived from PUBLIC_SURFACE, not hand-kept.
    assert MVP_MCP_TOOL_NAMES == _EXPECTED_MVP
    # POST_MVP == REGISTERED_POST_MVP (all entries registered -> LOCKED empty).
    assert POST_MVP_MCP_TOOL_NAMES == REGISTERED_POST_MVP_MCP_TOOL_NAMES
    assert REGISTERED_MCP_TOOL_NAMES == (
        MVP_MCP_TOOL_NAMES | REGISTERED_POST_MVP_MCP_TOOL_NAMES
    )
    assert registered_mcp_tool_names() == REGISTERED_MCP_TOOL_NAMES


def test_registered_absent_split_is_disjoint_and_complete() -> None:
    # The two tool-name splits a surface merge flips between must never overlap,
    # and their union is exactly the guard's known vocabulary.
    registered = registered_mcp_tool_names()
    absent = ABSENT_MCP_TOOL_NAMES

    assert registered.isdisjoint(absent)
    assert known_mcp_tool_names() == registered | absent


def test_post_mvp_cli_commands_are_declared_but_locked() -> None:
    # Given: current CLI commands remain MVP-only at runtime.
    runtime_commands = {
        entry.name
        for entry in PUBLIC_SURFACE.cli_commands
        if entry.stage is SurfaceStage.MVP
    }
    declared_post_mvp = {
        entry.name
        for entry in PUBLIC_SURFACE.cli_commands
        if entry.stage is SurfaceStage.POST_MVP
    }

    # When: docs describe the post-MVP command roadmap.
    # Then: locked commands are visible to planning without being runtime commands.
    assert {"init", "serve", "index", "scan", "status", "doctor"} <= runtime_commands
    assert declared_post_mvp >= {
        "report",
        "reset",
        "watch",
        "findings",
        "next",
        "explain",
    }
    assert runtime_commands.isdisjoint(declared_post_mvp)


def test_registered_post_mvp_cli_commands_satisfy_plan_audit() -> None:
    registered_post_mvp = {
        entry.name
        for entry in PUBLIC_SURFACE.cli_commands
        if entry.stage is SurfaceStage.POST_MVP and entry.registered
    }
    locked_post_mvp = {
        entry.name
        for entry in PUBLIC_SURFACE.cli_commands
        if entry.stage is SurfaceStage.POST_MVP and not entry.registered
    }

    assert registered_post_mvp >= POST_MVP_CLI_COMMAND_NAMES
    assert locked_post_mvp == set()
