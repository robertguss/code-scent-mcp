import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict, Field

from codescent.core.models import IndexedFile, ProjectConfig
from codescent.engine.inventory import build_file_inventory
from codescent.services.repo_index import RepoIndexService
from codescent.services.search import SearchService
from codescent.storage import RepositoryStorage, initialize_storage


class SearchPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    path: str
    score: float = Field(ge=0)
    reasons: tuple[str, ...]
    snippet: str | None = None


def test_search_files_exact_and_fuzzy(tmp_path: Path) -> None:
    # Hermetic copy of the fixture: the committed .codescent accumulates frecency
    # and findings written by other tests in the same run, which would otherwise
    # make this exact-ordering assertion depend on shared, mutating signal state.
    repo = tmp_path / "python-basic"
    _ = shutil.copytree(
        "tests/fixtures/python-basic",
        repo,
        ignore=shutil.ignore_patterns(".codescent"),
    )
    service = SearchService(repo)

    exact = service.search_files("config", limit=5)
    fuzzy = service.search_files("cnfig", limit=5)
    typo = service.search_files("payrol", limit=5)

    exact_payloads = tuple(SearchPayload.model_validate(result) for result in exact)
    fuzzy_payloads = tuple(SearchPayload.model_validate(result) for result in fuzzy)
    typo_payloads = tuple(SearchPayload.model_validate(result) for result in typo)

    # Path search routes through fff (typo-resistant fuzzy_paths), so the
    # top match is still correct for exact, fuzzy, and typo queries, but the
    # reason tag is fff's `fff_path` rather than the native exact/fuzzy tags.
    assert exact_payloads[0].path == "src/acme_tasks/config.py"
    assert "fff_path" in exact_payloads[0].reasons
    assert fuzzy_payloads[0].path == "src/acme_tasks/config.py"
    assert "fff_path" in fuzzy_payloads[0].reasons
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


def test_search_changed_files_filters_to_git_and_index_changes(
    tmp_path: Path,
) -> None:
    git_repo = tmp_path / "git-repo"
    git_repo.mkdir()
    source = git_repo / "src" / "app.py"
    clean_source = git_repo / "src" / "clean.py"
    test_source = git_repo / "tests" / "test_app.py"
    new_source = git_repo / "src" / "new_module.py"
    ignored_runtime = git_repo / ".codescent" / "debug.py"
    source.parent.mkdir(parents=True)
    test_source.parent.mkdir(parents=True)
    ignored_runtime.parent.mkdir(parents=True)
    _ = source.write_text("def run() -> None:\n    pass\n")
    _ = clean_source.write_text("def clean() -> None:\n    pass\n")
    _ = test_source.write_text("def test_run() -> None:\n    pass\n")
    _ = ignored_runtime.write_text("SHOULD_NOT_APPEAR = True\n")
    _run_git(git_repo, "init")
    _run_git(git_repo, "config", "user.email", "codescent@example.test")
    _run_git(git_repo, "config", "user.name", "CodeScent Test")
    _run_git(git_repo, "add", "src/app.py", "src/clean.py", "tests/test_app.py")
    _run_git(git_repo, "commit", "-m", "initial")

    _ = source.write_text("def run() -> None:\n    print('changed')\n")
    _ = test_source.write_text("def test_run() -> None:\n    assert True\n")
    _run_git(git_repo, "add", "tests/test_app.py")
    _ = new_source.write_text("def new_module() -> None:\n    pass\n")

    git_results = SearchService(git_repo).search_changed_files(limit=20)
    git_paths = {result["path"] for result in git_results}

    assert git_paths == {
        "src/app.py",
        "src/new_module.py",
        "tests/test_app.py",
    }
    assert "src/clean.py" not in git_paths
    assert all(".codescent" not in result["path"] for result in git_results)
    assert all("changed_file" in result["reasons"] for result in git_results)

    plain_repo = tmp_path / "plain-repo"
    plain_source = plain_repo / "src" / "plain.py"
    plain_source.parent.mkdir(parents=True)
    _ = plain_source.write_text("def plain() -> None:\n    pass\n")
    _ = RepoIndexService(plain_repo).index_repo()
    _ = plain_source.write_text("def plain() -> None:\n    print('changed')\n")

    plain_results = SearchService(plain_repo).search_changed_files(limit=20)

    assert tuple(result["path"] for result in plain_results) == ("src/plain.py",)
    assert "changed_file" in plain_results[0]["reasons"]


def test_search_todos_and_tests_service_rank_bounded_results(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "workflow.py"
    test_source = repo / "tests" / "test_workflow.py"
    ignored_runtime = repo / ".codescent" / "notes.py"
    source.parent.mkdir(parents=True)
    test_source.parent.mkdir(parents=True)
    ignored_runtime.parent.mkdir(parents=True)
    _ = source.write_text(
        """def route_workflow() -> None:
    pass
# TODO: route workflow retries
# FIXME: route workflow cancellation
# HACK: temporary workflow owner fallback
""",
    )
    _ = test_source.write_text(
        """from src.workflow import route_workflow

def test_route_workflow() -> None:
    route_workflow()
""",
    )
    _ = ignored_runtime.write_text("# TODO: ignored runtime state\n")

    service = SearchService(repo)
    todo_results = service.search_todos("workflow", limit=2)
    test_results = service.search_tests(
        "workflow",
        path="src/workflow.py",
        symbol="route_workflow",
        finding_id="python.large_function:src/workflow.py",
        limit=5,
    )

    assert len(todo_results) == 2
    assert {result["marker"] for result in todo_results} <= {"TODO", "FIXME", "HACK"}
    assert all(result["path"] == "src/workflow.py" for result in todo_results)
    assert all(".codescent" not in result["path"] for result in todo_results)
    assert test_results[0]["path"] == "tests/test_workflow.py"
    assert "likely_test" in test_results[0]["reasons"]
    assert "symbol_match" in test_results[0]["reasons"]


def test_multi_search_content_uses_one_inventory_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    billing = repo / "src" / "billing.py"
    workflow = repo / "src" / "workflow.py"
    billing.parent.mkdir(parents=True)
    _ = billing.write_text("TODO: reconcile billing\nbilling_total = 10\n")
    _ = workflow.write_text("TODO: route workflow\nworkflow_state = 'billing'\n")
    inventory_calls = 0

    def counting_build_file_inventory(
        root: Path | str,
        *,
        config: ProjectConfig | None = None,
    ) -> tuple[IndexedFile, ...]:
        nonlocal inventory_calls
        inventory_calls += 1
        return build_file_inventory(root, config=config)

    # multi_search_content builds the inventory once inside search_run's
    # content_results_for_queries, so the counter is patched there.
    monkeypatch.setattr(
        "codescent.services.search_run.build_file_inventory",
        counting_build_file_inventory,
    )

    results = SearchService(repo).multi_search_content(
        ("TODO", "billing"),
        limit=5,
    )
    payloads = tuple(SearchPayload.model_validate(result) for result in results)
    paths = tuple(payload.path for payload in payloads)

    assert inventory_calls == 1
    assert paths == tuple(dict.fromkeys(paths))
    assert set(paths) == {"src/billing.py", "src/workflow.py"}
    assert all(payload.snippet is not None for payload in payloads)
    assert all("query:TODO" in payload.reasons for payload in payloads)
    assert all("query:billing" in payload.reasons for payload in payloads)


def test_frecency_and_pagination_affect_rank_without_unbounded_results(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source_a = repo / "src" / "alpha_target.py"
    source_b = repo / "src" / "beta_target.py"
    source_c = repo / "src" / "case_target.py"
    source_a.parent.mkdir(parents=True)
    _ = source_a.write_text("lowercase_marker = True\n")
    _ = source_b.write_text("lowercase_marker = True\n")
    _ = source_c.write_text("CamelCaseMarker = True\n")

    service = SearchService(repo)
    initial = service.search_files("target", limit=2)
    _ = service.search_files("beta_target", limit=1)
    _ = service.search_files("beta_target", limit=1)
    boosted = service.search_files("target", limit=2)
    lower_case_content = service.search_content("camelcasemarker", limit=5)
    smart_case_content = service.search_content("CamelCaseMarker", limit=5)
    first_page = service.search_files_page("target", limit=1)
    second_page = service.search_files_page(
        "target",
        limit=1,
        cursor=first_page["next_cursor"],
    )
    state = initialize_storage(repo)

    with RepositoryStorage(state).read_connection() as connection:
        rows: list[tuple[str, str, float]] = connection.execute(
            "select path, signal, weight from frecency_signals order by path, signal",
        ).fetchall()

    assert initial[0]["path"] == "src/alpha_target.py"
    assert boosted[0]["path"] == "src/beta_target.py"
    assert "frecency" in boosted[0]["reasons"]
    assert tuple(result["path"] for result in lower_case_content) == (
        "src/case_target.py",
    )
    assert tuple(result["path"] for result in smart_case_content) == (
        "src/case_target.py",
    )
    assert first_page["next_cursor"] == "1"
    assert len(first_page["results"]) == 1
    assert len(second_page["results"]) == 1
    assert first_page["results"][0]["path"] != second_page["results"][0]["path"]
    assert rows
    assert all("beta_target" not in signal for _, signal, _ in rows)


def _disable_fff(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the native floor so the empty-result fuzzy fallback is exercised
    # deterministically; fff runs its own fuzzy matching that would otherwise
    # answer these NL queries before the native fallback ever fires.
    def _no_backend(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "codescent.services.search.select_search_backend",
        _no_backend,
    )


def test_search_content_fuzzy_fallback_tags_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_fff(monkeypatch)
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "hooks.py").write_text(
        """\
def build_hook_payload(event):
    # augment the payload with metadata
    payload = {}
    return payload
""",
    )

    results = SearchService(repo).search_content("hook augment payload", limit=20)

    assert results
    assert any("fuzzy" in result["reasons"] for result in results)


def test_search_files_fuzzy_fallback_tags_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_fff(monkeypatch)
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    for name in ("payroll_ledger.py", "config_loader.py", "widget_factory.py"):
        _ = (repo / "src" / name).write_text("def run() -> int:\n    return 1\n")

    results = SearchService(repo).search_files(
        "monthly staff payroll disbursement schedule",
        limit=20,
    )
    by_path = {result["path"]: result for result in results}

    assert "src/payroll_ledger.py" in by_path
    assert "fuzzy" in by_path["src/payroll_ledger.py"]["reasons"]


def test_search_content_no_fuzzy_fallback_on_literal_hit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_fff(monkeypatch)
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "hooks.py").write_text(
        """\
def build_hook_payload(event):
    # augment the payload here
    return {}
""",
    )

    results = SearchService(repo).search_content("augment the payload", limit=20)

    assert results
    assert all("fuzzy" not in result["reasons"] for result in results)


def test_search_absent_term_returns_empty_without_fuzzy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_fff(monkeypatch)
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "hooks.py").write_text("def run() -> int:\n    return 1\n")

    results = SearchService(repo).search_content("zzqqxx7f3a9b4c2e", limit=20)

    assert results == ()


def _run_git(repo: Path, *args: str) -> None:
    _ = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
