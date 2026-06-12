from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from codescent.core.models import ProjectConfig
from codescent.engine.packs_ts import TS_EXTENSIONS, parse_typescript_file
from codescent.engine.parsers.python import ParsedPythonFile, parse_python_file
from codescent.engine.rules.python import scan_python_health
from codescent.engine.rules.ts_react_next import scan_ts_react_next_health

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.engine.rules.model import CodeHealthFinding

PYTHON_LANGUAGE_PACK = "python"
PYTHON_RULE_PACK = "python-maintainability"
TYPESCRIPT_LANGUAGE_PACK = "typescript"
TYPESCRIPT_RULE_PACK = "ts-react-next"


class ParseFile(Protocol):
    def __call__(self, path: Path | str, relative_path: str) -> ParsedPythonFile: ...


class RuleScanner(Protocol):
    def __call__(
        self,
        root: Path | str,
        config: ProjectConfig,
    ) -> tuple[CodeHealthFinding, ...]: ...


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
    config: ProjectConfig

    def parser_for_language(self, language: str) -> ParseFile | None:
        for pack in self.language_packs:
            if language in pack.languages:
                return pack.parse_file
        return None

    def scan_rule_packs(self, root: Path | str) -> tuple[CodeHealthFinding, ...]:
        findings: list[CodeHealthFinding] = []
        for pack in self.rule_packs:
            findings.extend(pack.scan(root, self.config))
        return tuple(findings)


def build_pack_registry(config: ProjectConfig | None = None) -> PackRegistry:
    project_config = config or ProjectConfig()
    language_packs = _language_packs(project_config.language_packs)
    rule_packs = _rule_packs(project_config.rule_packs)
    return PackRegistry(
        language_packs=language_packs,
        rule_packs=rule_packs,
        config=project_config,
    )


def _language_packs(enabled: tuple[str, ...]) -> tuple[LanguagePack, ...]:
    packs: list[LanguagePack] = []
    if PYTHON_LANGUAGE_PACK not in enabled:
        return _typescript_language_packs(enabled)
    packs.append(
        LanguagePack(
            name=PYTHON_LANGUAGE_PACK,
            languages=("python",),
            suffixes=(".py", ".pyi"),
            parse_file=parse_python_file,
        ),
    )
    packs.extend(_typescript_language_packs(enabled))
    return tuple(packs)


def _typescript_language_packs(enabled: tuple[str, ...]) -> tuple[LanguagePack, ...]:
    if TYPESCRIPT_LANGUAGE_PACK not in enabled:
        return ()
    return (
        LanguagePack(
            name=TYPESCRIPT_LANGUAGE_PACK,
            languages=("javascript", "typescript"),
            suffixes=TS_EXTENSIONS,
            parse_file=parse_typescript_file,
        ),
    )


def _rule_packs(enabled: tuple[str, ...]) -> tuple[RulePack, ...]:
    packs: list[RulePack] = []
    if PYTHON_RULE_PACK in enabled:
        packs.append(
            RulePack(
                name=PYTHON_RULE_PACK,
                languages=("python",),
                scan=_scan_python_health,
            ),
        )
    if TYPESCRIPT_RULE_PACK in enabled:
        packs.append(
            RulePack(
                name=TYPESCRIPT_RULE_PACK,
                languages=("javascript", "typescript"),
                scan=_scan_ts_react_next_health,
            ),
        )
    return tuple(packs)


def _scan_python_health(
    root: Path | str,
    config: ProjectConfig,
) -> tuple[CodeHealthFinding, ...]:
    return scan_python_health(root, config=config)


def _scan_ts_react_next_health(
    root: Path | str,
    config: ProjectConfig,
) -> tuple[CodeHealthFinding, ...]:
    return scan_ts_react_next_health(root, config=config)
