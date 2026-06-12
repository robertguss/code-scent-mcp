from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.core.models import ProjectConfig
from codescent.core.paths import resolve_repo_root

if TYPE_CHECKING:
    from pathlib import Path

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
    return _render_config_payload(
        {
            "include": list(config.include),
            "exclude": list(config.exclude),
            "generated": list(config.generated),
            "vendor": list(config.vendor),
            "build": list(config.build),
            "language_packs": list(config.language_packs),
            "framework_packs": list(config.framework_packs),
            "rule_packs": list(config.rule_packs),
        },
    )


def _render_config_payload(payload: dict[str, TomlValue]) -> str:
    lines: list[str] = []
    for key, value in payload.items():
        if isinstance(value, dict):
            lines.append("")
            lines.append(f"[{key}]")
            lines.extend(
                f"{child_key} = {_toml_value(child_value)}"
                for child_key, child_value in value.items()
            )
            continue
        lines.append(f"{key} = {_toml_value(value)}")
    lines.append("")
    return "\n".join(lines)


def _toml_value(value: TomlValue) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if value is None:
        return '""'
    raise TypeError(type(value).__name__)
