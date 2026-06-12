from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from codescent.core.models import ProjectConfig
from codescent.engine.parsers.python import ParsedPythonFile, parse_python_file
from codescent.engine.rules.python import scan_python_health

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.engine.rules.model import CodeHealthFinding

PYTHON_LANGUAGE_PACK = "python"
PYTHON_RULE_PACK = "python-maintainability"


class ParseFile(Protocol):
    def __call__(self, path: Path | str, relative_path: str) -> ParsedPythonFile: ...


class RuleScanner(Protocol):
    def __call__(self, root: Path | str) -> tuple[CodeHealthFinding, ...]: ...


@dataclass(frozen=True, slots=True)
class LanguagePack:
    name: str
    languages: tuple[str, ...]
    suffixes: tuple[str, ...]
    parse_file: ParseFile


@dataclass(frozen=True, slots=True)
class RulePack:
    name: str
    languages: tuple[str, ...]
    scan: RuleScanner


@dataclass(frozen=True, slots=True)
class PackRegistry:
    language_packs: tuple[LanguagePack, ...]
    rule_packs: tuple[RulePack, ...]

    def parser_for_language(self, language: str) -> ParseFile | None:
        for pack in self.language_packs:
            if language in pack.languages:
                return pack.parse_file
        return None

    def scan_rule_packs(self, root: Path | str) -> tuple[CodeHealthFinding, ...]:
        findings: list[CodeHealthFinding] = []
        for pack in self.rule_packs:
            findings.extend(pack.scan(root))
        return tuple(findings)


def build_pack_registry(config: ProjectConfig | None = None) -> PackRegistry:
    project_config = config or ProjectConfig()
    language_packs = _language_packs(project_config.language_packs)
    rule_packs = _rule_packs(project_config.rule_packs)
    return PackRegistry(language_packs=language_packs, rule_packs=rule_packs)


def _language_packs(enabled: tuple[str, ...]) -> tuple[LanguagePack, ...]:
    if PYTHON_LANGUAGE_PACK not in enabled:
        return ()
    return (
        LanguagePack(
            name=PYTHON_LANGUAGE_PACK,
            languages=("python",),
            suffixes=(".py", ".pyi"),
            parse_file=parse_python_file,
        ),
    )


def _rule_packs(enabled: tuple[str, ...]) -> tuple[RulePack, ...]:
    if PYTHON_RULE_PACK not in enabled:
        return ()
    return (
        RulePack(
            name=PYTHON_RULE_PACK,
            languages=("python",),
            scan=_scan_python_health,
        ),
    )


def _scan_python_health(root: Path | str) -> tuple[CodeHealthFinding, ...]:
    return scan_python_health(root)
