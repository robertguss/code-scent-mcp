from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from codescent.core.models import ProjectConfig
from codescent.core.paths import resolve_repo_root

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import BaseModel

type TomlValue = (
    None | bool | int | float | str | list[TomlValue] | dict[str, TomlValue]
)


@dataclass(frozen=True, slots=True)
class ConfigService:
    repo_root: Path | str

    def load(self) -> ProjectConfig:
        repo_root = resolve_repo_root(self.repo_root)
        config_path = repo_root / ".codescent" / "config.toml"
        if not config_path.exists():
            return ProjectConfig()
        return ProjectConfig.model_validate(_parse_config(config_path))

    def save(self, config: ProjectConfig) -> None:
        repo_root = resolve_repo_root(self.repo_root)
        config_path = repo_root / ".codescent" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        _ = config_path.write_text(_render_config(config))

    def save_rule_packs(self, rule_packs: tuple[str, ...]) -> ProjectConfig:
        repo_root = resolve_repo_root(self.repo_root)
        config = self.load().model_copy(update={"rule_packs": rule_packs})
        config_path = repo_root / ".codescent" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if config_path.exists():
            raw = _parse_raw_config(config_path)
            raw["rule_packs"] = list(rule_packs)
            _ = config_path.write_text(_render_config_payload(raw))
        else:
            _ = config_path.write_text(_render_config(config))
        return config


def _parse_config(config_path: Path) -> dict[str, TomlValue]:
    raw = _parse_raw_config(config_path)
    project = raw.get("project")
    if isinstance(project, dict):
        raw = {key: value for key, value in raw.items() if key != "project"}
    return raw


def _parse_raw_config(config_path: Path) -> dict[str, TomlValue]:
    raw: dict[str, TomlValue] = tomllib.loads(config_path.read_text())
    return raw


def _render_config(config: ProjectConfig) -> str:
    payload: dict[str, TomlValue] = {
        "include": list(config.include),
        "exclude": list(config.exclude),
        "generated": list(config.generated),
        "vendor": list(config.vendor),
        "build": list(config.build),
        "language_packs": list(config.language_packs),
        "framework_packs": list(config.framework_packs),
        "rule_packs": list(config.rule_packs),
        "coverage_path": config.coverage_path,
        "auto_bootstrap": config.auto_bootstrap,
        "commands": _section(config.commands),
        "token_budgets": _section(config.token_budgets),
        "privacy": _section(config.privacy),
        "architecture": _section(config.architecture),
        "thresholds": _section(config.thresholds),
        "ratchet": _section(config.ratchet),
        "adaptive": _section(config.adaptive),
    }
    if config.llm is not None:
        payload["llm"] = _section(config.llm)
    return _render_config_payload(payload)


def _section(model: BaseModel) -> dict[str, TomlValue]:
    # mode="json" normalizes tuples to lists so the TOML renderer can emit them.
    return cast("dict[str, TomlValue]", model.model_dump(mode="json"))


def _render_config_payload(payload: dict[str, TomlValue]) -> str:
    lines: list[str] = []
    for key, value in payload.items():
        if not isinstance(value, dict):
            lines.append(f"{key} = {_toml_value(value)}")
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        lines.append("")
        lines.append(f"[{key}]")
        lines.extend(
            f"{child_key} = {_toml_value(child_value)}"
            for child_key, child_value in value.items()
        )
    lines.append("")
    return "\n".join(lines)


def _toml_value(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        items = cast("list[TomlValue]", value)
        return "[" + ", ".join(_toml_value(item) for item in items) + "]"
    if isinstance(value, dict):
        table = cast("dict[str, TomlValue]", value)
        return (
            "{ "
            + ", ".join(
                f"{child_key} = {_toml_value(child_value)}"
                for child_key, child_value in table.items()
            )
            + " }"
        )
    if value is None:
        return '""'
    raise TypeError(type(value).__name__)
