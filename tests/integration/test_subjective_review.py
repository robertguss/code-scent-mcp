import sqlite3
from contextlib import closing
from pathlib import Path

from codescent.services.subjective_review import (
    FakeSubjectiveReviewProvider,
    SubjectiveReviewService,
)
from codescent.storage import initialize_storage


def test_subjective_review_persists_separately_from_deterministic_findings(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """STATUS = "pending-review"
OTHER_STATUS = "pending-review"
THIRD_STATUS = "pending-review"


def load_config() -> str:
    return STATUS
""",
    )

    result = SubjectiveReviewService(repo).review(
        provider_name="fake",
        provider=FakeSubjectiveReviewProvider(),
        allow_subjective=True,
    )
    state = initialize_storage(repo)

    assert result.enabled is True
    assert result.provider == "fake"
    assert result.subjective_findings
    assert result.subjective_findings[0].subjective is True
    assert result.subjective_findings[0].provider == "fake"
    with closing(sqlite3.connect(state.database_path)) as connection:
        subjective_rows: list[tuple[int]] = connection.execute(
            "select count(*) from subjective_findings",
        ).fetchall()
        deterministic_rows: list[tuple[int]] = connection.execute(
            "select count(*) from findings",
        ).fetchall()
    subjective_count = subjective_rows[0][0]
    deterministic_count = deterministic_rows[0][0]
    assert subjective_count == len(result.subjective_findings)
    assert deterministic_count == 0
