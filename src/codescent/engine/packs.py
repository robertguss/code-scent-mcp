from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from codescent.core.models import ProjectConfig
from codescent.engine.packs_generic import scan_generic_health
from codescent.engine.packs_go import GO_EXTENSIONS, parse_go_file, scan_go_health
from codescent.engine.packs_ts import TS_EXTENSIONS, parse_typescript_file
from codescent.engine.parsers.python import ParsedPythonFile, parse_python_file
from codescent.engine.rules.architecture import scan_architecture
from codescent.engine.rules.import_cycles import scan_import_cycles
from codescent.engine.rules.knowledge_silo import scan_knowledge_silos
from codescent.engine.rules.python import scan_python_health
from codescent.engine.rules.test_quality import (
    scan_python_test_quality,
    scan_typescript_test_quality,
)
from codescent.engine.rules.ts_react_next import scan_ts_react_next_health

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.engine.rules.model import CodeHealthFinding

PYTHON_LANGUAGE_PACK = "python"
PYTHON_RULE_PACK = "python-maintainability"
TYPESCRIPT_LANGUAGE_PACK = "typescript"
TYPESCRIPT_RULE_PACK = "ts-react-next"
GO_LANGUAGE_PACK = "go"
GO_RULE_PACK = "go-maintainability"
ARCHITECTURE_RULE_PACK = "architecture"
KNOWLEDGE_SILO_RULE_PACK = "knowledge-silo"
GENERIC_RULE_PACK = "generic"


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
    rule_packs = _rule_packs(
        project_config.rule_packs,
        generic_fallback=project_config.generic_fallback,
    )
    return PackRegistry(
        language_packs=language_packs,
        rule_packs=rule_packs,
        config=project_config,
    )


def _language_packs(enabled: tuple[str, ...]) -> tuple[LanguagePack, ...]:
    packs: list[LanguagePack] = []
    if PYTHON_LANGUAGE_PACK in enabled:
        packs.append(
            LanguagePack(
                name=PYTHON_LANGUAGE_PACK,
                languages=("python",),
                suffixes=(".py", ".pyi"),
                parse_file=parse_python_file,
            ),
        )
    packs.extend(_typescript_language_packs(enabled))
    # Specific Go pack. It must stay ahead of any future generic-fallback pack so
    # parser_for_language() resolves `.go` to this pack rather than the fallback.
    packs.extend(_go_language_packs(enabled))
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


def _go_language_packs(enabled: tuple[str, ...]) -> tuple[LanguagePack, ...]:
    if GO_LANGUAGE_PACK not in enabled:
        return ()
    return (
        LanguagePack(
            name=GO_LANGUAGE_PACK,
            languages=("go",),
            suffixes=GO_EXTENSIONS,
            parse_file=parse_go_file,
        ),
    )


def _rule_packs(
    enabled: tuple[str, ...],
    *,
    generic_fallback: bool = True,
) -> tuple[RulePack, ...]:
    packs: list[RulePack] = []
    packs.append(
        RulePack(
            name=ARCHITECTURE_RULE_PACK,
            languages=("python",),
            scan=_scan_architecture_health,
        ),
    )
    # Always-on (like architecture): the git-derived bus-factor signal spans both
    # languages from one log pass and self-disables at runtime when there is no
    # git history, so it needs no config gate.
    packs.append(
        RulePack(
            name=KNOWLEDGE_SILO_RULE_PACK,
            languages=("python", "typescript"),
            scan=_scan_knowledge_silos,
        ),
    )
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
    if GO_RULE_PACK in enabled:
        packs.append(
            RulePack(
                name=GO_RULE_PACK,
                languages=("go",),
                scan=_scan_go_health,
            ),
        )
    # Generic text-only fallback. Registered LAST so it is lowest precedence: it
    # only inspects files no specific pack owns (the specific suffixes are
    # reserved inside packs_generic), so python/typescript/go always win for
    # their own files. Gated by its own flag (default on) rather than rule_packs
    # membership -- like architecture/knowledge-silo, it is an always-applicable
    # cross-language pack, not one of the per-language opt-in packs.
    if generic_fallback:
        packs.append(
            RulePack(
                name=GENERIC_RULE_PACK,
                languages=("generic",),
                scan=_scan_generic_health,
            ),
        )
    return tuple(packs)


def _scan_architecture_health(
    root: Path | str,
    config: ProjectConfig,
) -> tuple[CodeHealthFinding, ...]:
    return scan_architecture(root, config=config)


def _scan_python_health(
    root: Path | str,
    config: ProjectConfig,
) -> tuple[CodeHealthFinding, ...]:
    # Import-cycle detection is a whole-repo Python maintainability concern, so
    # it ships inside the python-maintainability pack rather than as a separate
    # registered pack (keeps the pack set stable; gated by the same config flag).
    return (
        *scan_python_health(root, config=config),
        *scan_import_cycles(root, config=config),
        *scan_python_test_quality(root, config=config),
    )


def _scan_ts_react_next_health(
    root: Path | str,
    config: ProjectConfig,
) -> tuple[CodeHealthFinding, ...]:
    return (
        *scan_ts_react_next_health(root, config=config),
        *scan_typescript_test_quality(root, config=config),
    )


def _scan_knowledge_silos(
    root: Path | str,
    config: ProjectConfig,
) -> tuple[CodeHealthFinding, ...]:
    return scan_knowledge_silos(root, config=config)


def _scan_go_health(
    root: Path | str,
    config: ProjectConfig,
) -> tuple[CodeHealthFinding, ...]:
    return scan_go_health(root, config=config)


def _scan_generic_health(
    root: Path | str,
    config: ProjectConfig,
) -> tuple[CodeHealthFinding, ...]:
    return scan_generic_health(root, config=config)
