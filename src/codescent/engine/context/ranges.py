from dataclasses import dataclass
from pathlib import Path


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
    lines = (repo_root / relative_path).read_text().splitlines()
    selected = lines[start_line - 1 : capped_end]
    return SourceRange(
        path=relative_path,
        start_line=start_line,
        end_line=capped_end,
        source="\n".join(selected),
    )
