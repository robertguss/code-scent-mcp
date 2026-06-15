from __future__ import annotations

from typing import TYPE_CHECKING, Final

from codescent.core.models import ProjectConfig
from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.engine.parsers.python import ParsedPythonFile, parse_python_file
from codescent.engine.rules.model import (
    CodeHealthFinding,
    FindingSpec,
    build_finding,
)

if TYPE_CHECKING:
    from pathlib import Path

MAX_ARCHITECTURE_FINDINGS: Final = 100


def scan_architecture(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
) -> tuple[CodeHealthFinding, ...]:
    repo_root = resolve_repo_root(root)
    project_config = config or ProjectConfig()
    if not project_config.architecture.rules:
        return ()

    findings: list[CodeHealthFinding] = []
    for item in build_file_inventory(repo_root, config=project_config):
        if item.language != "python":
            continue
        parsed = parse_python_file(repo_root / item.path, item.path)
        for rule in project_config.architecture.rules:
            if not _matches_layer(parsed.path, rule.layer):
                continue
            for imported in parsed.imports:
                module = _normalized_import_module(parsed, imported.module)
                if _matches_forbidden_import(module, rule.forbidden_imports):
                    findings.append(
                        build_finding(
                            FindingSpec(
                                rule_id="architecture.boundary_violation",
                                title="Architecture boundary violation",
                                message=(
                                    f"{parsed.path} imports {module}, which is "
                                    f"forbidden for {rule.layer}."
                                ),
                                file_path=parsed.path,
                                symbol=None,
                                severity="warning",
                                confidence=0.95,
                                evidence={
                                    "layer": rule.layer,
                                    "imported": module,
                                    "line": imported.line,
                                },
                                suggested_action=(
                                    "Remove the cross-layer import or move the "
                                    "shared code to an allowed layer."
                                ),
                            ),
                        ),
                    )
                    if len(findings) >= MAX_ARCHITECTURE_FINDINGS:
                        return tuple(findings)
    return tuple(findings)


def _matches_layer(path: str, layer: str) -> bool:
    normalized = layer.strip().strip("/")
    return bool(normalized) and (
        path == normalized or path.startswith(f"{normalized}/")
    )


def _matches_forbidden_import(module: str, forbidden_imports: tuple[str, ...]) -> bool:
    return any(
        module == forbidden or module.startswith(f"{forbidden}.")
        for forbidden in forbidden_imports
    )


def _normalized_import_module(parsed: ParsedPythonFile, module: str) -> str:
    if not module.startswith("."):
        return module

    level = len(module) - len(module.lstrip("."))
    tail = module[level:]
    package_parts = parsed.module.split(".")[:-level]
    if not tail:
        return ".".join(package_parts)
    return ".".join((*package_parts, tail))
