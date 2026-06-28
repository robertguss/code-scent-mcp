from typing import ClassVar

from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict


class GuideStepModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    step: int
    action: str
    tools: tuple[str, ...]


class GuideGroupModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    group: str
    reach_for_when: str
    tools: tuple[str, ...]
    omitted_count: int


class GuidePayloadModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    server: str
    summary: str
    workflow: tuple[GuideStepModel, ...]
    tool_groups: tuple[GuideGroupModel, ...]
    safety_boundaries: tuple[str, ...]
    tool_count: int

    def tool_names(self) -> set[str]:
        return {name for group in self.tool_groups for name in group.tools}


def guide_text(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text
