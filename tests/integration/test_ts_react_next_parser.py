from pathlib import Path

from codescent.services.repo_index import RepoIndexService
from codescent.storage import RepositoryStorage, initialize_storage

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "ts-react-next-basic"


def test_ts_pack_indexes_symbols_imports_components_hooks_and_routes() -> None:
    result = RepoIndexService(FIXTURE_ROOT).index_repo()
    storage = RepositoryStorage(initialize_storage(FIXTURE_ROOT))

    with storage.read_connection() as connection:
        file_rows: list[tuple[str, str]] = connection.execute(
            "select path, language from files order by path",
        ).fetchall()
        symbol_rows: list[tuple[str, str, str]] = connection.execute(
            "select name, qualified_name, kind from symbols",
        ).fetchall()
        reference_rows: list[tuple[str]] = connection.execute(
            "select reference_text from symbol_references",
        ).fetchall()
        files = dict(file_rows)
        symbols = {
            (name, qualified_name, kind) for name, qualified_name, kind in symbol_rows
        }
        references = {reference for (reference,) in reference_rows}

    assert result.indexed_files == 8
    assert files["components/task-list.tsx"] == "typescript"
    assert files["components/task-card.jsx"] == "javascript"
    assert files["app/api/tasks/route.ts"] == "typescript"
    assert files["pages/legacy.jsx"] == "javascript"
    assert ("TaskList", "components.task-list.TaskList", "component") in symbols
    assert ("TaskCard", "components.task-card.TaskCard", "component") in symbols
    assert ("useTasks", "hooks.useTasks.useTasks", "hook") in symbols
    assert ("GET", "app.api.tasks.route.GET", "route") in symbols
    assert ("LegacyTasksPage", "pages.legacy.LegacyTasksPage", "component") in symbols
    assert {"react", "../hooks/useTasks", "./task-card.jsx"} <= references
