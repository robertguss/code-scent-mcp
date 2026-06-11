from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.services.context import ContextService

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class SuggestedTests:
    commands: tuple[str, ...]
    likely_tests: tuple[str, ...]
    executes_in_v1: bool


@dataclass(frozen=True, slots=True)
class VerificationService:
    repo_root: Path | str

    def suggest_tests(self, file_path: str) -> SuggestedTests:
        context = ContextService(self.repo_root).get_file_context(file_path)
        likely_tests = context["likely_tests"]
        commands = tuple(f"pytest {path}" for path in likely_tests)
        return SuggestedTests(
            commands=commands or ("pytest",),
            likely_tests=likely_tests,
            executes_in_v1=False,
        )
