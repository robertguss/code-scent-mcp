from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import override


class ErrorCode(StrEnum):
    INVALID_REPO_ROOT = "invalid_repo_root"
    PATH_OUTSIDE_ROOT = "path_outside_root"
    STALE_INDEX = "stale_index"
    MISSING_INDEX = "missing_index"
    UNSUPPORTED_FILE = "unsupported_file"
    PARSE_FAILURE = "parse_failure"
    CORRUPT_DATABASE = "corrupt_database"
    MISSING_GIT = "missing_git"
    NON_GIT_REPOSITORY = "non_git_repository"
    CONCURRENT_WRITE = "concurrent_write"


class ErrorSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def _empty_details() -> Mapping[str, str]:
    return MappingProxyType({})


@dataclass(slots=True)
class CodeScentError(Exception):
    code: ErrorCode
    message: str
    severity: ErrorSeverity
    details: Mapping[str, str] = field(default_factory=_empty_details)

    def __post_init__(self) -> None:
        frozen_details = MappingProxyType(dict(self.details))
        object.__setattr__(self, "details", frozen_details)
        Exception.__init__(self, str(self))

    @override
    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"

    def to_payload(self) -> dict[str, str | dict[str, str]]:
        return {
            "code": self.code.value,
            "message": self.message,
            "severity": self.severity.value,
            "details": dict(self.details),
        }
