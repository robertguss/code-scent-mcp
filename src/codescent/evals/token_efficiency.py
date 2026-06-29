"""Token-efficiency benchmark (plan unit U2 / bead P0.2).

The scoreboard for the navigator roadmap: it proves the token savings of the
CodeScent tools over the naive ``grep + read the whole matching file`` workflow
an agent falls back to without them. Three scenarios -- find a symbol, locate a
content string, and gather task context -- are each run two ways and counted
with the local :func:`codescent.core.token_estimate.estimate_tokens` helper
(KTD-4). The per-scenario and overall deltas are written by
``evals/run_token_efficiency.py`` to a committed baseline JSON so every later
phase can report its token drop against this reference.

The run is deterministic and bounded: the fixture repo is copied into a scratch
directory, its runtime ``.codescent`` state is rebuilt cold, and only relative
paths ever enter the payloads, so the numbers reproduce against the checked-in
``tests/fixtures/python-basic`` fixture. No network, no model encoder.

The CodeScent path uses the real services (``ContextService.find_symbol``,
``SearchService.search_content``, ``start_task``); the naive path replicates a
recursive grep followed by a full read of every matching file.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from codescent.core.token_estimate import estimate_tokens
from codescent.mcp.repo_tools import start_task
from codescent.services.code_health import CodeHealthService
from codescent.services.context import ContextService
from codescent.services.search import SearchService

# Queries chosen so the naive path is forced to read a non-trivial file (or
# several) while the CodeScent path returns only bounded metadata.
SYMBOL_QUERY = "config"
CONTENT_QUERY = "export"
TASK_QUERY = "export"

_IGNORED_DIRS = frozenset({".codescent", ".git"})
_RATIO_DIGITS = 6


class ScenarioReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    scenario: str
    codescent_tokens: int
    naive_tokens: int
    delta: int
    ratio: float


class SummaryReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    codescent_tokens: int
    naive_tokens: int
    delta: int
    ratio: float


class TokenEfficiencyReport(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    repo: str
    scenarios: tuple[ScenarioReport, ...]
    summary: SummaryReport


def build_token_efficiency_report(repo: Path) -> TokenEfficiencyReport:
    """Run every scenario against ``repo`` and return the token-delta report.

    The fixture is copied into a scratch directory and its runtime state rebuilt
    cold, so the result depends only on the checked-in source and reproduces
    exactly across runs.

    Args:
        repo: Path to the fixture repository to benchmark.

    Returns:
        The per-scenario and summary token report.
    """
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch) / "repo"
        _ = shutil.copytree(repo, work)
        shutil.rmtree(work / ".codescent", ignore_errors=True)
        # Warm the index + findings once so the services report steady state.
        _ = CodeHealthService(work).scan()
        scenarios = (
            _scenario(
                "find_symbol",
                _serialize(ContextService(work).find_symbol(SYMBOL_QUERY)),
                _naive_payload(work, SYMBOL_QUERY),
            ),
            _scenario(
                "search_content",
                _serialize(SearchService(work).search_content(CONTENT_QUERY)),
                _naive_payload(work, CONTENT_QUERY),
            ),
            _scenario(
                "start_task",
                _serialize(start_task(TASK_QUERY, str(work))),
                _naive_payload(work, TASK_QUERY),
            ),
        )
    return TokenEfficiencyReport(
        repo=repo.as_posix(),
        scenarios=scenarios,
        summary=_summarize(scenarios),
    )


def _scenario(name: str, codescent_text: str, naive_text: str) -> ScenarioReport:
    codescent_tokens = estimate_tokens(codescent_text)
    naive_tokens = estimate_tokens(naive_text)
    return ScenarioReport(
        scenario=name,
        codescent_tokens=codescent_tokens,
        naive_tokens=naive_tokens,
        delta=naive_tokens - codescent_tokens,
        ratio=_ratio(codescent_tokens, naive_tokens),
    )


def _summarize(scenarios: tuple[ScenarioReport, ...]) -> SummaryReport:
    codescent_tokens = sum(item.codescent_tokens for item in scenarios)
    naive_tokens = sum(item.naive_tokens for item in scenarios)
    return SummaryReport(
        codescent_tokens=codescent_tokens,
        naive_tokens=naive_tokens,
        delta=naive_tokens - codescent_tokens,
        ratio=_ratio(codescent_tokens, naive_tokens),
    )


def _ratio(codescent_tokens: int, naive_tokens: int) -> float:
    if naive_tokens == 0:
        return 0.0
    return round(codescent_tokens / naive_tokens, _RATIO_DIGITS)


def _serialize(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


def _naive_payload(repo_root: Path, term: str) -> str:
    """Replicate ``grep -rn <term>`` then reading each matching file in full.

    The returned text is what an agent without CodeScent would have to pull into
    context: the grep hit lines plus the entire body of every matched file.

    Args:
        repo_root: Root of the (scratch copy of the) repository to scan.
        term: The search term, matched case-insensitively per line.

    Returns:
        The concatenated naive payload an agent would read into context.
    """
    needle = term.lower()
    sections: list[str] = []
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or _IGNORED_DIRS.intersection(path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative = path.relative_to(repo_root).as_posix()
        hits = [
            f"{relative}:{number}:{line}"
            for number, line in enumerate(text.splitlines(), start=1)
            if needle in line.lower()
        ]
        if not hits:
            continue
        sections.extend(hits)
        sections.append(f"===== {relative} =====")
        sections.append(text)
    return "\n".join(sections)
