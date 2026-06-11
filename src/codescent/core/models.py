from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConfigSource(StrEnum):
    DEFAULTS = "defaults"
    PROJECT_CONFIG = "project_config"
    CLI_FLAGS = "cli_flags"
    TOOL_ARGS = "tool_args"


class FindingStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DEFERRED = "deferred"
    WONTFIX = "wontfix"
    IGNORED = "ignored"
    REGRESSED = "regressed"
    NEEDS_REVIEW = "needs_review"


class RepoConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    root_path: str
    include: tuple[str, ...] = (".",)
    exclude: tuple[str, ...] = (
        ".codescent",
        ".git",
        ".venv",
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
        "data",
        "archive",
        "dist",
        "build",
        "coverage",
    )


class IndexedFile(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    path: str
    language: str
    hash: str
    size_bytes: int = Field(ge=0)
    line_count: int = Field(ge=0)
    is_test: bool = False
    is_generated: bool = False


class Symbol(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    name: str
    qualified_name: str
    kind: str
    file_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)


class Finding(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    id: str
    stable_key: str
    rule_id: str
    title: str
    message: str
    file_path: str
    severity: str
    confidence: float = Field(ge=0, le=1)
    status: FindingStatus = FindingStatus.OPEN


class ScanRun(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    id: str
    status: str
    files_scanned: int = Field(ge=0)
    findings_created: int = Field(ge=0)
    findings_resolved: int = Field(ge=0)


class RepoStatus(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    root_path: str
    index_fresh: bool
    indexed_files: int = Field(ge=0)
    finding_count: int = Field(ge=0)
    database_ok: bool


class SearchResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    path: str
    score: float = Field(ge=0)
    reasons: tuple[str, ...]
    snippet: str | None = None


class ContextOptions(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    default_token_budget: int = Field(default=3000, ge=1)
    source_line_cap: int = Field(default=80, ge=1, le=200)
    max_source_line_cap: int = Field(default=200, ge=80, le=200)
    include_source: bool = False


class ContextPack(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    summary: str
    relevant_files: tuple[str, ...]
    relevant_symbols: tuple[str, ...]
    relevant_tests: tuple[str, ...]
    risk_notes: tuple[str, ...]
    token_estimate: int = Field(ge=0)
    options: ContextOptions = Field(default_factory=ContextOptions)


class SearchOptions(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    limit: int = Field(default=20, ge=1)
    max_limit: int = 100

    @field_validator("limit", mode="after")
    @classmethod
    def clamp_limit(cls, value: int) -> int:
        return min(value, 100)


class RefactorPlan(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    goal: str
    non_goals: tuple[str, ...]
    affected_files: tuple[str, ...]
    steps: tuple[str, ...]
    risk_level: str
    fallback: str


class SuggestedVerification(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command: str
    reason: str
    executes_in_v1: bool = False


class EvalResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    name: str
    passed: bool
    score: float = Field(ge=0, le=1)
    metrics: dict[str, float]
