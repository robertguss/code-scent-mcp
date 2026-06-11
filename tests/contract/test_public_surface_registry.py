from codescent.core.public_surface import (
    LOCKED_POST_MVP_MCP_TOOL_NAMES,
    MVP_MCP_TOOL_NAMES,
    POST_MVP_MCP_TOOL_NAMES,
    PUBLIC_SURFACE,
    REGISTERED_POST_MVP_MCP_TOOL_NAMES,
    SurfaceStage,
)


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
    assert {
        entry.name
        for entry in PUBLIC_SURFACE.mcp_tools
        if entry.stage is SurfaceStage.POST_MVP and entry.registered
    } == REGISTERED_POST_MVP_MCP_TOOL_NAMES
    assert {
        entry.name
        for entry in PUBLIC_SURFACE.mcp_tools
        if entry.stage is SurfaceStage.POST_MVP and not entry.registered
    } == LOCKED_POST_MVP_MCP_TOOL_NAMES
    assert registered_mvp.isdisjoint(declared_post_mvp)


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
