from dataclasses import dataclass
from pathlib import Path

from codescent.engine.source_read import MAX_SOURCE_BYTES, read_source_lines


@dataclass(frozen=True, slots=True)
class SourceRange:
    path: str
    start_line: int
    end_line: int
    source: str

    def to_payload(self) -> dict[str, str | int]:
        return {
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "source": self.source,
        }


def source_range(
    repo_root: Path,
    relative_path: str,
    *,
    start_line: int,
    end_line: int,
    line_cap: int,
) -> SourceRange:
    capped_end = min(end_line, start_line + max(line_cap, 1) - 1)
    source = read_source_lines(repo_root / relative_path)
    if source.lines is None:
        return SourceRange(
            path=relative_path,
            start_line=start_line,
            end_line=start_line,
            source=f"[source omitted: file exceeds {MAX_SOURCE_BYTES} byte budget]",
        )
    lines = source.lines
    selected = lines[start_line - 1 : capped_end]
    return SourceRange(
        path=relative_path,
        start_line=start_line,
        end_line=capped_end,
        source="\n".join(selected),
    )
