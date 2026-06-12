from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.services.config import ConfigService

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class RuleConfigReport:
    enabled_rule_packs: tuple[str, ...]
    disabled_rule_packs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RulesService:
    repo_root: Path | str

    def get_rules(self) -> RuleConfigReport:
        config = ConfigService(self.repo_root).load()
        return RuleConfigReport(
            enabled_rule_packs=config.rule_packs,
            disabled_rule_packs=(),
        )
