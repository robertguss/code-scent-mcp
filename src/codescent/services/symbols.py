from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.engine.packs import build_pack_registry
from codescent.services.config import ConfigService

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.engine.parsers.python import ParsedPythonFile


@dataclass(frozen=True, slots=True)
class SymbolExtraction:
    files: tuple[ParsedPythonFile, ...]


@dataclass(frozen=True, slots=True)
class SymbolService:
    repo_root: Path | str

    def extract(self) -> SymbolExtraction:
        repo_root = resolve_repo_root(self.repo_root)
        registry = build_pack_registry(ConfigService(repo_root).load())
        parsed_files = tuple(
            parser(repo_root / item.path, item.path)
            for item in build_file_inventory(repo_root)
            for parser in (registry.parser_for_language(item.language),)
            if parser is not None
        )
        return SymbolExtraction(files=parsed_files)
