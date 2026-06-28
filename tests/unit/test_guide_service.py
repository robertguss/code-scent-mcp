import json

from codescent.core.public_surface import registered_mcp_tool_names
from codescent.services.guide import (
    MAX_TOOLS_PER_GROUP,
    SAFETY_BOUNDARIES,
    WORKFLOW,
    build_guide,
)


def test_guide_is_pure_and_deterministic() -> None:
    assert build_guide() == build_guide()


def test_guide_tool_set_equals_registered_surface() -> None:
    guide = build_guide()
    names = {name for group in guide["tool_groups"] for name in group["tools"]}

    assert names == set(registered_mcp_tool_names())
    assert guide["tool_count"] == len(registered_mcp_tool_names())


def test_every_tool_has_a_non_empty_group_and_one_line_purpose() -> None:
    guide = build_guide()
    seen: dict[str, int] = {}
    for group in guide["tool_groups"]:
        assert group["group"]
        assert group["reach_for_when"]
        assert "\n" not in group["reach_for_when"]
        for name in group["tools"]:
            assert name
            seen[name] = seen.get(name, 0) + 1

    # Each registered tool appears under exactly one group.
    assert set(seen) == set(registered_mcp_tool_names())
    assert all(count == 1 for count in seen.values())


def test_workflow_covers_the_recommended_steps_with_registered_tools() -> None:
    registered = set(registered_mcp_tool_names())
    assert build_guide()["workflow"] == WORKFLOW
    assert [step["step"] for step in WORKFLOW] == list(range(1, len(WORKFLOW) + 1))
    assert len(WORKFLOW) == 9
    for step in WORKFLOW:
        assert step["action"]
        for tool in step["tools"]:
            assert tool in registered


def test_safety_boundaries_are_present() -> None:
    boundaries = " ".join(build_guide()["safety_boundaries"]).lower()
    assert SAFETY_BOUNDARIES
    assert "read-only" in boundaries
    assert "no runtime network" in boundaries
    assert ".codescent/" in boundaries
    assert "bounded" in boundaries


def test_guide_leaks_no_analyzed_source() -> None:
    serialized = json.dumps(build_guide())
    for leaked in ("source_content", "source_ranges", "file_path", "/home/"):
        assert leaked not in serialized


def test_per_group_tool_lists_are_bounded() -> None:
    for group in build_guide()["tool_groups"]:
        assert len(group["tools"]) <= MAX_TOOLS_PER_GROUP
        assert group["omitted_count"] == 0
