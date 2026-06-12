from codescent.core.public_surface import (
    LOCKED_POST_MVP_MCP_TOOL_NAMES,
    MVP_MCP_TOOL_NAMES,
    POST_MVP_CLI_COMMAND_NAMES,
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


def test_context_optimization_tools_are_registered_context_surface() -> None:
    # Given: Headroom-inspired retrieval and stats are public MCP context tools.
    expected_context_tools = {"retrieve_result", "context_stats"}

    # When: the public surface registry is inspected.
    registered_context_tools = {
        entry.name
        for entry in PUBLIC_SURFACE.mcp_tools
        if entry.stage is SurfaceStage.POST_MVP
        and entry.registered
        and entry.group == "context"
    }

    # Then: the new tools register without later guidance/compression tools.
    assert expected_context_tools <= registered_context_tools
    assert "project_learnings" not in registered_context_tools
    assert "project_guidance" not in registered_context_tools
    assert "compress_generic_output" not in registered_context_tools
    assert "retrieve_original_output" not in registered_context_tools


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
