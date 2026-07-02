from codescent.core.public_surface import (
    ABSENT_MCP_TOOL_NAMES,
    LOCKED_POST_MVP_MCP_TOOL_NAMES,
    MVP_MCP_TOOL_NAMES,
    POST_MVP_CLI_COMMAND_NAMES,
    POST_MVP_MCP_TOOL_NAMES,
    PUBLIC_SURFACE,
    REGISTERED_POST_MVP_MCP_TOOL_NAMES,
    SurfaceStage,
    known_mcp_tool_names,
    registered_mcp_tool_names,
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
    assert {
        entry.name
        for entry in PUBLIC_SURFACE.mcp_tools
        if entry.stage is SurfaceStage.POST_MVP and not entry.registered
    } == LOCKED_POST_MVP_MCP_TOOL_NAMES
    assert registered_mvp.isdisjoint(declared_post_mvp)
    assert ABSENT_POST_MVP_MCP_TOOL_NAMES.isdisjoint(
        {entry.name for entry in PUBLIC_SURFACE.mcp_tools}
    )


def test_registered_locked_absent_split_is_disjoint_and_complete() -> None:
    # The three tool-name splits a surface merge flips between must never
    # overlap, and their union is exactly the guard's known vocabulary.
    registered = registered_mcp_tool_names()
    locked = LOCKED_POST_MVP_MCP_TOOL_NAMES
    absent = ABSENT_MCP_TOOL_NAMES

    assert registered.isdisjoint(locked)
    assert registered.isdisjoint(absent)
    assert locked.isdisjoint(absent)
    assert known_mcp_tool_names() == registered | locked | absent


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
