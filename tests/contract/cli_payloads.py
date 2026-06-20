from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)


class ScanPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    findings_created: int
    rule_ids: tuple[str, ...]
    finding_ids: tuple[str, ...] = ()


class InitPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    state_dir: str


class IndexPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    indexed_files: int


class StatusPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    index_fresh: bool
    indexed_files: int


class DoctorChecks(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    database_ok: bool
    config_ok: bool
    mcp_available: bool


class DoctorPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    checks: DoctorChecks


class ErrorPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    code: str


class ConfigPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    include: tuple[str, ...]
    exclude: tuple[str, ...]
    language_packs: tuple[str, ...]
    framework_packs: tuple[str, ...]
    rule_packs: tuple[str, ...]
    commands: dict[str, tuple[str, ...]]
    token_budgets: dict[str, int]
    privacy: dict[str, bool]


class RulesPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    enabled_rule_packs: tuple[str, ...]
    disabled_rule_packs: tuple[str, ...]


class WatchPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    indexed_files: int
    changed_files: tuple[str, ...]


class ResetPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    deleted: bool
    paths: tuple[str, ...]


class CiPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    risk_level: str
    changed_file_health: tuple[dict[str, JsonValue], ...]
    suggested_tests: tuple[str, ...]


class CiBaselinePayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    files_recorded: int
    finding_count: int


class CiRatchetPayload(CiPayload):
    ratchet_enabled: bool
    ratchet_regressions: tuple[dict[str, JsonValue], ...]
    baseline_exists: bool
    base_ref: str
    new_finding_count: int
    resolved_count: int
    new_findings: tuple[dict[str, JsonValue], ...]
