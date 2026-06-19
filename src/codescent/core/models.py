from enum import StrEnum
from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_PAGE_LIMIT = 100


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


class CommandHints(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    test: tuple[str, ...] = ()
    typecheck: tuple[str, ...] = ()
    lint: tuple[str, ...] = ()
    build: tuple[str, ...] = ()


class TokenBudgets(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    context: int = Field(default=3000, ge=1)
    file: int = Field(default=800, ge=1)
    dashboard: int = Field(default=10000, ge=1)


class PrivacySettings(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    runtime_network: bool = False
    allow_llm_review: bool = False


class LlmSettings(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    provider: str
    model: str


class ArchitectureRule(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    layer: str
    forbidden_imports: tuple[str, ...] = ()


class ArchitectureRules(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    rules: tuple[ArchitectureRule, ...] = ()


class MaintainabilityThresholds(BaseModel):
    """Tunable size/count thresholds for the deterministic maintainability rules.

    Defaults are calibrated for real codebases — they flag genuinely large or
    repetitive code, not the median file. Lower them per-repo (or use
    ``strict()``) to surface more findings on small inputs.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    # Python
    large_file_lines: int = Field(default=300, ge=1)
    large_function_lines: int = Field(default=50, ge=1)
    large_class_lines: int = Field(default=200, ge=1)
    too_many_imports: int = Field(default=20, ge=1)
    deep_nesting: int = Field(default=4, ge=1)
    todo_cluster_size: int = Field(default=3, ge=1)
    duplicate_literal_min_count: int = Field(default=4, ge=2)
    duplicate_literal_min_length: int = Field(default=8, ge=1)
    # Relative ("large for this repository") thresholds. These add an
    # outlier-for-this-repo finding flavor on top of the absolute thresholds,
    # catching files/functions/classes that are unusually large for the repo
    # even when under the absolute floor. Uses a robust IQR outlier rule so it
    # fires only on genuine outliers, not a fixed fraction of the codebase.
    relative_thresholds_enabled: bool = True
    relative_outlier_iqr_multiplier: float = Field(default=1.5, ge=0)
    relative_min_sample_size: int = Field(default=12, ge=2)
    # TypeScript / React / Next
    ts_large_component_lines: int = Field(default=150, ge=1)
    ts_too_many_hooks: int = Field(default=8, ge=1)
    ts_too_many_props: int = Field(default=8, ge=1)
    ts_too_many_exports: int = Field(default=10, ge=1)
    ts_route_handler_lines: int = Field(default=40, ge=1)

    @classmethod
    def strict(cls) -> Self:
        """The historical aggressive thresholds.

        Retained for the tiny test fixtures and deterministic evals, which need a
        rich finding set on small inputs. Not recommended for real repositories —
        these flag most files and were the cause of the signal-to-noise problem.
        """
        return cls(
            large_file_lines=70,
            large_function_lines=25,
            large_class_lines=60,
            too_many_imports=12,
            deep_nesting=4,
            todo_cluster_size=3,
            duplicate_literal_min_count=3,
            duplicate_literal_min_length=4,
            relative_thresholds_enabled=False,
            ts_large_component_lines=12,
            ts_too_many_hooks=1,
            ts_too_many_props=3,
            ts_too_many_exports=3,
            ts_route_handler_lines=3,
        )


class RatchetSettings(BaseModel):
    """CI ratchet: fail only on new debt, not the pre-existing backlog.

    The ratchet compares the current scan against an accepted baseline of finding
    stable keys. A finding is *new* when its stable key is absent from the
    baseline; CI fails only when a new finding is at least ``fail_on_new_severity``
    severe. ``base_ref`` (empty = disabled) scopes the check to files changed
    since that git ref.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    enabled: bool = False
    base_ref: str = ""
    fail_on_new_severity: str = "warning"
    require_non_negative_net_health: bool = False


class AdaptiveSettings(BaseModel):
    """Adaptive, self-calibrating findings driven by the repo's own verdicts.

    Confidence recalibration nudges a rule's confidence toward its empirical
    accept rate (resolved vs wontfix/ignored) once enough verdicts exist; below
    ``min_sample_size`` the base confidence is used unchanged (cold start). The
    adjustment is bounded by ``max_confidence_delta`` and never falls below
    ``confidence_floor``. Learned suppression flags rule+directory scopes that
    have been dismissed at least ``suppression_threshold`` times.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    confidence_recalibration: bool = True
    learned_suppression: bool = False
    min_sample_size: int = Field(default=8, ge=1)
    max_confidence_delta: float = Field(default=0.2, ge=0, le=1)
    confidence_floor: float = Field(default=0.3, ge=0, le=1)
    suppression_threshold: int = Field(default=5, ge=1)


class ProjectConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    include: tuple[str, ...] = (".",)
    exclude: tuple[str, ...] = RepoConfig(root_path=".").exclude
    generated: tuple[str, ...] = ()
    vendor: tuple[str, ...] = ()
    build: tuple[str, ...] = ()
    language_packs: tuple[str, ...] = ("python", "typescript")
    framework_packs: tuple[str, ...] = ()
    rule_packs: tuple[str, ...] = ("python-maintainability", "ts-react-next")
    coverage_path: str = "coverage.xml"
    commands: CommandHints = Field(default_factory=CommandHints)
    token_budgets: TokenBudgets = Field(default_factory=TokenBudgets)
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)
    architecture: ArchitectureRules = Field(default_factory=ArchitectureRules)
    thresholds: MaintainabilityThresholds = Field(
        default_factory=MaintainabilityThresholds,
    )
    ratchet: RatchetSettings = Field(default_factory=RatchetSettings)
    adaptive: AdaptiveSettings = Field(default_factory=AdaptiveSettings)
    llm: LlmSettings | None = None

    def with_overrides(
        self,
        *,
        cli_flags: dict[str, object] | None = None,
        tool_args: dict[str, object] | None = None,
    ) -> Self:
        payload: dict[str, object] = self.model_dump(mode="python")
        for overrides in (cli_flags or {}, tool_args or {}):
            payload.update(overrides)
        return self.model_validate(payload)


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


class EnvelopeMode(StrEnum):
    EXACT = "exact"
    SUMMARIZED = "summarized"
    FILTERED = "filtered"
    SAMPLE = "sample"
    TRUNCATED = "truncated"


class EnvelopeConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ResponseEnvelope(BaseModel):
    """Stable wrapper for bounded result payloads.

    Existing item schemas stay stable. Envelope metadata is additive and should
    be updated in lockstep with the public contract for any surface that adopts
    it.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    kind: str
    mode: EnvelopeMode
    summary: str
    items: tuple[object, ...] = Field(default_factory=tuple)
    omitted_count: int = Field(default=0, ge=0)
    original_result_id: str | None = None
    retrieval_available: bool = False
    retrieval_hints: tuple[str, ...] = Field(default_factory=tuple)
    confidence: EnvelopeConfidence = EnvelopeConfidence.HIGH
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    stats: dict[str, int | float] | None = None


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


class PageOptions(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    limit: int = 20
    offset: int = 0

    @field_validator("limit", mode="after")
    @classmethod
    def clamp_limit(cls, value: int) -> int:
        return min(max(value, 1), MAX_PAGE_LIMIT)

    @field_validator("offset", mode="after")
    @classmethod
    def clamp_offset(cls, value: int) -> int:
        return max(value, 0)


class SearchOptions(PageOptions):
    pass


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
