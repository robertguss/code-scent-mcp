from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from codescent.services.repo_index import RepoIndexService
from codescent.services.search import SearchService
from codescent.storage import RepositoryStorage, initialize_storage


class SearchPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    path: str
    score: float = Field(ge=0)
    reasons: tuple[str, ...]
    snippet: str | None = None


def test_search_files_exact_and_fuzzy() -> None:
    service = SearchService("tests/fixtures/python-basic")

    exact = service.search_files("config", limit=5)
    fuzzy = service.search_files("cnfig", limit=5)
    typo = service.search_files("payrol", limit=5)

    exact_payloads = tuple(SearchPayload.model_validate(result) for result in exact)
    fuzzy_payloads = tuple(SearchPayload.model_validate(result) for result in fuzzy)
    typo_payloads = tuple(SearchPayload.model_validate(result) for result in typo)

    assert exact_payloads[0].path == "src/acme_tasks/config.py"
    assert "exact_path" in exact_payloads[0].reasons
    assert fuzzy_payloads[0].path == "src/acme_tasks/config.py"
    assert "fuzzy_path" in fuzzy_payloads[0].reasons
    assert typo_payloads[0].path == "src/acme_tasks/payroll.py"
    assert typo_payloads[0].reasons
    assert len(fuzzy_payloads) <= 5


def test_search_content_returns_bounded_snippets(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """alpha
TODO: first task should be visible
middle
TODO: second task should not make this unbounded
omega
""",
    )

    results = SearchService(repo).search_content("todo", limit=20, line_budget=1)
    payloads = tuple(SearchPayload.model_validate(result) for result in results)

    assert len(payloads) == 2
    assert all(payload.path == "src/app.py" for payload in payloads)
    assert all("content_match" in payload.reasons for payload in payloads)
    snippets = tuple(payload.snippet for payload in payloads)

    assert all(snippet is not None for snippet in snippets)
    assert all(
        snippet is not None and len(snippet.splitlines()) == 1 for snippet in snippets
    )
    assert snippets[0] is not None
    assert "TODO: first task should be visible" in snippets[0]


def test_search_ranks_changed_files_and_storage_has_frecency_placeholder(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("def target() -> None:\n    pass\n")
    _ = RepoIndexService(repo).index_repo()
    _ = source.write_text("def target() -> None:\n    print('changed')\n")

    results = SearchService(repo).search_files("app", limit=1)
    state = initialize_storage(repo)
    with RepositoryStorage(state).read_connection() as connection:
        cursor = connection.execute("select 1 from frecency_signals limit 0")

    payload = SearchPayload.model_validate(results[0])

    assert cursor.description is not None
    assert payload.path == "src/app.py"
    assert "changed_file" in payload.reasons
