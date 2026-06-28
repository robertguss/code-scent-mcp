from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class RulePrecisionPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    rule_id: str
    accepted: int
    dismissed: int
    sample_size: int
    acceptance_precision: float | None
    suppression_candidates: int


class HealthTrendPointPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    date: str
    accepted: int
    dismissed: int
    acceptance_precision: float | None


class PrecisionPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    accepted: int
    dismissed: int
    sample_size: int
    acceptance_precision: float | None
    rules: tuple[RulePrecisionPayload, ...]
    trend: tuple[HealthTrendPointPayload, ...]

    def rule(self, rule_id: str) -> RulePrecisionPayload:
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        raise KeyError(rule_id)
