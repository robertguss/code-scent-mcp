from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from codescent.core.paths import normalize_repo_path, resolve_repo_root
from codescent.services.context import ContextService
from codescent.services.git import git_changed_paths
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class SuggestedTests:
    commands: tuple[str, ...]
    likely_tests: tuple[str, ...]
    executes_in_v1: bool


@dataclass(frozen=True, slots=True)
class SelectedTests:
    changed_files: tuple[str, ...]
    test_files: tuple[str, ...]
    command: str
    executes_in_v1: bool


@dataclass(frozen=True, slots=True)
class VerificationRecommendation:
    recommendation_id: int
    recommended_commands: tuple[str, ...]
    likely_tests: tuple[str, ...]
    missing_characterization_tests: tuple[str, ...]
    executes: bool


@dataclass(frozen=True, slots=True)
class VerificationService:
    repo_root: Path | str
    auto_refresh: bool = True

    def suggest_tests(self, file_path: str) -> SuggestedTests:
        # A finding can reference a file that is not in the code index (empty
        # path or a non-indexed doc/.md file); get_file_context raises LookupError
        # for those. Degrade to no likely tests rather than crashing the tool.
        try:
            likely_tests = (
                ContextService(self.repo_root, auto_refresh=self.auto_refresh)
                .get_file_context(file_path)["likely_tests"]
                if file_path
                else ()
            )
        except LookupError:
            likely_tests = ()
        commands = tuple(f"pytest {path}" for path in likely_tests)
        return SuggestedTests(
            commands=commands or ("pytest",),
            likely_tests=likely_tests,
            executes_in_v1=False,
        )

    def select_tests(self, *, paths: tuple[str, ...] | None = None) -> SelectedTests:
        repo_root = resolve_repo_root(self.repo_root)
        changed_files = _changed_files(repo_root, paths)
        context = ContextService(repo_root, auto_refresh=self.auto_refresh)
        test_files: set[str] = set()

        for path in changed_files:
            if _is_test_path(path):
                test_files.add(path)
                continue
            if not _is_python_source_path(path):
                continue

            test_files.update(_likely_tests_for_path(context, path))

        selected = tuple(sorted(test_files))
        return SelectedTests(
            changed_files=changed_files,
            test_files=selected,
            command=_pytest_command(selected),
            executes_in_v1=False,
        )

    def verify_change(self, finding_id: str) -> VerificationRecommendation:
        state = initialize_storage(self.repo_root)
        finding = FindingRepository(RepositoryStorage(state)).get_finding(finding_id)
        suggested = self.suggest_tests(finding.file_path)
        reason = f"Verify deterministic finding {finding.rule_id} without execution."
        with RepositoryStorage(state).write_transaction() as connection:
            cursor = connection.execute(
                """
                insert into suggested_verifications (
                    finding_id,
                    command,
                    reason,
                    executes_in_v1
                ) values (?, ?, ?, ?)
                """,
                (
                    finding.id,
                    suggested.commands[0],
                    reason,
                    0,
                ),
            )
        recommendation_id = cursor.lastrowid
        if recommendation_id is None:
            recommendation_id = 0
        return VerificationRecommendation(
            recommendation_id=recommendation_id,
            recommended_commands=suggested.commands,
            likely_tests=suggested.likely_tests,
            missing_characterization_tests=(),
            executes=False,
        )


def _changed_files(repo_root: Path, paths: tuple[str, ...] | None) -> tuple[str, ...]:
    if paths is None:
        return tuple(sorted(git_changed_paths(repo_root)))
    return tuple(sorted(_repo_relative_path(repo_root, path) for path in paths))


def _repo_relative_path(repo_root: Path, path: str) -> str:
    return normalize_repo_path(repo_root, path).relative_to(repo_root).as_posix()


def _likely_tests_for_path(context: ContextService, path: str) -> set[str]:
    try:
        file_context = context.get_file_context(path)
        related = context.get_related_files(path, limit=20)
    except LookupError:
        return set()

    tests = set(file_context["likely_tests"])
    for result in related["results"]:
        related_path = result["path"]
        if _is_test_path(related_path) or "test_match" in result["reasons"]:
            tests.add(related_path)
    return tests


def _is_python_source_path(path: str) -> bool:
    return path.endswith((".py", ".pyi"))


def _is_test_path(path: str) -> bool:
    parsed = PurePosixPath(path)
    return parsed.name.startswith("test_") or "tests" in parsed.parts


def _pytest_command(test_files: tuple[str, ...]) -> str:
    if not test_files:
        return "pytest"
    return f"pytest {' '.join(test_files)}"
