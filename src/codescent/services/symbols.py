from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.engine.parsers.python import ParsedPythonFile, parse_python_file

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class SymbolExtraction:
    files: tuple[ParsedPythonFile, ...]


@dataclass(frozen=True, slots=True)
class SymbolService:
    repo_root: Path | str

    def extract(self) -> SymbolExtraction:
        repo_root = resolve_repo_root(self.repo_root)
        parsed_files = tuple(
            parse_python_file(repo_root / item.path, item.path)
            for item in build_file_inventory(repo_root)
            if item.language == "python"
        )
        return SymbolExtraction(files=parsed_files)
