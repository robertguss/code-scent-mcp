from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

MAX_SOURCE_BYTES: Final = 1_000_000


@dataclass(frozen=True, slots=True)
class SourceBytes:
    content: bytes | None
    size_bytes: int
    oversized: bool


@dataclass(frozen=True, slots=True)
class SourceText:
    text: str | None
    size_bytes: int
    oversized: bool


@dataclass(frozen=True, slots=True)
class SourceLines:
    lines: tuple[str, ...] | None
    size_bytes: int
    oversized: bool


def read_source_bytes(
    path: Path,
    *,
    max_bytes: int = MAX_SOURCE_BYTES,
) -> SourceBytes:
    size_bytes = path.stat().st_size
    if size_bytes > max_bytes:
        return SourceBytes(content=None, size_bytes=size_bytes, oversized=True)
    return SourceBytes(
        content=path.read_bytes(),
        size_bytes=size_bytes,
        oversized=False,
    )


def read_source_text(
    path: Path,
    *,
    max_bytes: int = MAX_SOURCE_BYTES,
) -> SourceText:
    size_bytes = path.stat().st_size
    if size_bytes > max_bytes:
        return SourceText(text=None, size_bytes=size_bytes, oversized=True)
    return SourceText(text=path.read_text(), size_bytes=size_bytes, oversized=False)


def read_source_lines(
    path: Path,
    *,
    max_bytes: int = MAX_SOURCE_BYTES,
) -> SourceLines:
    result = read_source_text(path, max_bytes=max_bytes)
    if result.text is None:
        return SourceLines(
            lines=None,
            size_bytes=result.size_bytes,
            oversized=result.oversized,
        )
    return SourceLines(
        lines=tuple(result.text.splitlines()),
        size_bytes=result.size_bytes,
        oversized=False,
    )
