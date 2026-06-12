import pytest
from fastmcp import Client
from mcp.types import TextContent

from codescent.mcp.server import mcp

EXPECTED_PROMPTS = {
    "safe_refactor_finding",
    "investigate_symbol_before_editing",
    "add_characterization_tests",
    "review_changed_files_for_slop",
    "verify_risky_refactor",
    "improve_code_health",
}


@pytest.mark.anyio
async def test_prompt_resources_are_registered_and_safety_bounded() -> None:
    async with Client(mcp) as client:
        prompts = await client.list_prompts()
        rendered = await client.get_prompt(
            "safe_refactor_finding",
            {
                "repo": "tests/fixtures/python-basic",
                "finding_id": "python.todo_cluster:example",
            },
        )

    prompt_names = {prompt.name for prompt in prompts}
    assert prompt_names >= EXPECTED_PROMPTS
    listed = {prompt.name: prompt for prompt in prompts}
    assert listed["safe_refactor_finding"].description is not None
    assert listed["verify_risky_refactor"].arguments

    assert len(rendered.messages) == 1
    content = rendered.messages[0].content
    assert isinstance(content, TextContent)
    text = content.text
    assert "Do not edit source automatically" in text
    assert "Do not override local safety constraints" in text
    assert "Use CodeScent tools before broad file reads" in text
    assert "python.todo_cluster:example" in text
