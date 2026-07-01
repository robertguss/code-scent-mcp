"""U3: enrichment payload builder for the grep-injection hook.

Integration coverage against a real indexed fixture (AE2, R9, zero-match) plus
deterministic monkeypatched coverage for the git-modified health tag (AE3/R8),
which needs controlled ``git_modified``/``health`` inputs.
"""

import shutil
from pathlib import Path

import pytest

from codescent.core.token_estimate import estimate_tokens
from codescent.services import hook_payload
from codescent.services.hook_payload import build_payload
from codescent.services.hook_retrieval import HookMatch
from codescent.services.repo_index import RepoIndexService


def _copy_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "python-basic"
    _ = shutil.copytree(
        "tests/fixtures/python-basic",
        repo,
        ignore=shutil.ignore_patterns(".codescent"),
    )
    _ = RepoIndexService(repo).index_repo(full=True)
    return repo


def test_build_payload_shape_and_budget(tmp_path: Path) -> None:
    # Covers AE2/R6/R7/R9.
    repo = _copy_fixture(tmp_path)

    payload = build_payload(repo, "load_config")

    assert payload is not None
    assert "load_config" in payload
    assert "src/acme_tasks/config.py:" in payload  # repo-relative path:line (R7)
    assert "codescent" in payload  # pointer to codescent tools (R9)
    # At most five match lines (R6) plus header + pointer.
    body_lines = [line for line in payload.splitlines() if line.startswith("  ")]
    assert len(body_lines) <= 5
    assert estimate_tokens(payload) <= 240  # token budget (R9)


def test_build_payload_none_on_no_matches(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)

    assert build_payload(repo, "zzz_no_such_symbol_zzz") is None


def test_build_payload_health_tag_only_on_git_modified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Covers AE3/R8: only the git-modified match carries a risk/health tag.
    crafted = (
        HookMatch(
            path="src/changed.py",
            line=10,
            symbol_name="touched",
            symbol_kind="function",
            score=200.0,
            git_modified=True,
            health=("hotspot", "complex"),
        ),
        HookMatch(
            path="src/stable.py",
            line=20,
            symbol_name="untouched",
            symbol_kind="function",
            score=100.0,
            git_modified=False,
            health=(),
        ),
    )
    monkeypatch.setattr(hook_payload, "ranked_matches", lambda *a, **k: crafted)

    payload = build_payload(Path(), "touched")

    assert payload is not None
    changed_line = next(
        line for line in payload.splitlines() if "src/changed.py" in line
    )
    stable_line = next(line for line in payload.splitlines() if "src/stable.py" in line)
    assert "hotspot" in changed_line  # health tag present on modified file
    assert "hotspot" not in stable_line
    assert "⚠" not in stable_line  # no risk marker on the unmodified file


def test_build_payload_truncates_to_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Covers R9: oversized match lines are trimmed so the payload stays bounded.
    long_path = "src/" + ("very_long_directory_segment/" * 6) + "module.py"
    crafted = tuple(
        HookMatch(
            path=long_path,
            line=index,
            symbol_name="a_long_symbol_name_for_padding",
            symbol_kind="function",
            score=float(100 - index),
            git_modified=False,
            health=(),
        )
        for index in range(1, 6)
    )
    monkeypatch.setattr(hook_payload, "ranked_matches", lambda *a, **k: crafted)

    payload = build_payload(Path(), "padding")

    assert payload is not None
    assert estimate_tokens(payload) <= 240
    assert "codescent" in payload  # pointer survives truncation
