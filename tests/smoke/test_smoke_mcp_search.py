from pathlib import Path

from scripts.smoke_mcp import prepare_repo_for_tools


def test_search_changed_smoke_resets_runtime_state(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    state_file = repo / ".codescent" / "index.sqlite"
    source = repo / "src" / "app.py"
    state_file.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    _ = state_file.write_text("stale")
    _ = source.write_text("def run() -> None:\n    pass\n")

    prepare_repo_for_tools(repo, ("search_changed",))

    assert not state_file.parent.exists()
