from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.engine.packs import PYTHON_RULE_PACK, TYPESCRIPT_RULE_PACK
from codescent.services.config import ConfigService

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class RuleConfigReport:
    enabled_rule_packs: tuple[str, ...]
    disabled_rule_packs: tuple[str, ...]


KNOWN_RULE_PACKS = (PYTHON_RULE_PACK, TYPESCRIPT_RULE_PACK)


@dataclass(frozen=True, slots=True)
class RulesService:
    repo_root: Path | str

    def get_rules(self) -> RuleConfigReport:
        config = ConfigService(self.repo_root).load()
        return _report(config.rule_packs)

    def update_rules(self, enabled_rule_packs: tuple[str, ...]) -> RuleConfigReport:
        if any(pack not in KNOWN_RULE_PACKS for pack in enabled_rule_packs):
            return _report(ConfigService(self.repo_root).load().rule_packs)
        config = ConfigService(self.repo_root).save_rule_packs(enabled_rule_packs)
        return _report(config.rule_packs)

    def is_valid_rule_pack_selection(self, enabled_rule_packs: tuple[str, ...]) -> bool:
        return all(pack in KNOWN_RULE_PACKS for pack in enabled_rule_packs)


def _report(enabled_rule_packs: tuple[str, ...]) -> RuleConfigReport:
    disabled = tuple(
        pack for pack in KNOWN_RULE_PACKS if pack not in enabled_rule_packs
    )
    return RuleConfigReport(
        enabled_rule_packs=enabled_rule_packs,
        disabled_rule_packs=disabled,
    )
