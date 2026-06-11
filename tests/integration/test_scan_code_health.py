import sqlite3
from contextlib import closing
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict
from typer.testing import CliRunner

from codescent.cli.main import app


class ScanCliPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    status: str
    findings_created: int
    rule_ids: tuple[str, ...]
    findings: tuple["ScanFindingPayload", ...]


class ScanFindingPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    stable_key: str


def test_scan_persists_run_and_findings(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """STATUS = "pending-review"
OTHER_STATUS = "pending-review"
THIRD_STATUS = "pending-review"


def load_config() -> dict[str, str]:
    # TODO: split config
    # FIXME: preserve compatibility
    # HACK: keep old queue name
    return {"status": STATUS}
""",
    )

    result = CliRunner().invoke(app, ["scan", "--repo", str(repo), "--json"])
    payload = ScanCliPayload.model_validate_json(result.output)

    assert result.exit_code == 0
    assert payload.status == "complete"
    assert payload.findings_created >= 2
    assert "python.todo_cluster" in payload.rule_ids
    assert "python.changed_source_without_related_test" in payload.rule_ids
    assert all(finding.stable_key for finding in payload.findings)
    with closing(sqlite3.connect(repo / ".codescent" / "index.sqlite")) as connection:
        persisted_sql = "\n".join(connection.iterdump())

    assert 'INSERT INTO "scan_runs"' in persisted_sql
    assert "python.todo_cluster" in persisted_sql
    assert "python.duplicate_literal" in persisted_sql
    assert "python.changed_source_without_related_test" in persisted_sql
    assert "evidence_json" in persisted_sql
