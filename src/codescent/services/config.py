from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.core.models import ProjectConfig
from codescent.core.paths import resolve_repo_root

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class ConfigService:
    repo_root: Path | str

    def load(self) -> ProjectConfig:
        repo_root = resolve_repo_root(self.repo_root)
        config_path = repo_root / ".codescent" / "config.toml"
        if not config_path.exists():
            return ProjectConfig()
        return ProjectConfig.model_validate(_parse_config(config_path))


def _parse_config(config_path: Path) -> dict[str, object]:
    raw: dict[str, object] = tomllib.loads(config_path.read_text())
    project = raw.get("project")
    if isinstance(project, dict):
        raw = {key: value for key, value in raw.items() if key != "project"}
    return raw
