import sqlite3
from typing import Final

SCHEMA_VERSION: Final = 7

BASE_TABLE_STATEMENTS: Final[tuple[str, ...]] = (
    "create table if not exists schema_version (version integer not null)",
    """
    create table if not exists files (
        id integer primary key,
        path text not null unique,
        language text not null,
        hash text not null,
        size_bytes integer not null,
        line_count integer not null,
        git_status text,
        is_generated integer not null default 0,
        is_test integer not null default 0,
        last_indexed_at text
    )
    """,
    """
    create table if not exists symbols (
        id integer primary key,
        file_id integer not null references files(id) on delete cascade,
        name text not null,
        qualified_name text not null,
        kind text not null,
        signature text,
        start_line integer not null,
        end_line integer not null,
        exported integer not null default 0,
        confidence real not null
    )
    """,
    """
    create table if not exists imports (
        id integer primary key,
        source_file_id integer not null references files(id) on delete cascade,
        imported_path text not null,
        imported_symbol text,
        resolved_file_id integer references files(id),
        confidence real not null
    )
    """,
    """
    create table if not exists chunks (
        id integer primary key,
        file_id integer not null references files(id) on delete cascade,
        symbol_id integer references symbols(id) on delete set null,
        chunk_kind text not null,
        start_line integer not null,
        end_line integer not null,
        summary text,
        token_estimate integer not null default 0
    )
    """,
    """
    create table if not exists scan_runs (
        id text primary key,
        started_at text not null,
        completed_at text,
        index_version integer not null,
        rule_version text not null,
        files_scanned integer not null default 0,
        findings_created integer not null default 0,
        findings_resolved integer not null default 0,
        status text not null
    )
    """,
    """
    create table if not exists findings (
        id text primary key,
        stable_key text not null unique,
        rule_id text not null,
        file_id integer references files(id) on delete set null,
        symbol_id integer references symbols(id) on delete set null,
        severity text not null,
        confidence real not null,
        status text not null,
        title text not null,
        message text not null,
        evidence_json text not null,
        suggested_action text,
        first_seen_scan_id text references scan_runs(id),
        last_seen_scan_id text references scan_runs(id),
        resolved_at text
    )
    """,
    """
    create table if not exists finding_events (
        id integer primary key,
        finding_id text not null references findings(id) on delete cascade,
        event_type text not null,
        created_at text not null,
        details_json text not null
    )
    """,
    """
    create table if not exists suggested_verifications (
        id integer primary key,
        finding_id text references findings(id) on delete cascade,
        command text not null,
        reason text not null,
        executes_in_v1 integer not null default 0
    )
    """,
    """
    create table if not exists eval_runs (
        id text primary key,
        name text not null,
        started_at text not null,
        completed_at text,
        passed integer not null,
        score real not null,
        metrics_json text not null
    )
    """,
    """
    create table if not exists frecency_signals (
        id integer primary key,
        path text not null,
        signal text not null,
        weight real not null,
        updated_at text not null
    )
    """,
    """
    create table if not exists telemetry (
        id integer primary key,
        event_name text not null,
        created_at text not null,
        payload_json text not null
    )
    """,
)

MIGRATION_STATEMENTS: Final[dict[int, tuple[str, ...]]] = {
    3: (
        """
        create table if not exists symbol_references (
            id integer primary key,
            source_file_id integer not null references files(id) on delete cascade,
            source_symbol_id integer references symbols(id) on delete set null,
            target_file_id integer references files(id) on delete set null,
            target_symbol_id integer references symbols(id) on delete set null,
            reference_text text not null,
            start_line integer not null,
            end_line integer not null,
            confidence real not null
        )
        """,
        """
        create table if not exists call_edges (
            id integer primary key,
            caller_symbol_id integer references symbols(id) on delete cascade,
            callee_symbol_id integer references symbols(id) on delete set null,
            source_file_id integer not null references files(id) on delete cascade,
            target_file_id integer references files(id) on delete set null,
            call_text text not null,
            start_line integer not null,
            confidence real not null
        )
        """,
    ),
    4: (
        """
        create table if not exists subjective_findings (
            id text primary key,
            provider text not null,
            prompt text not null,
            file_path text not null,
            title text not null,
            message text not null,
            confidence real not null,
            created_at text not null
        )
        """,
    ),
    5: (
        """
        create table if not exists stored_results (
            id text primary key,
            project_id text not null,
            session_id text,
            tool_name text not null,
            input_json text not null,
            raw_result_json text not null,
            summary_json text,
            content_type text,
            raw_token_estimate integer,
            returned_token_estimate integer,
            created_at text not null,
            expires_at text,
            retrieval_count integer not null default 0
        )
        """,
        """
        create table if not exists session_events (
            id text primary key,
            project_id text not null,
            session_id text not null,
            event_type text not null,
            tool_name text,
            result_id text,
            payload_json text,
            created_at text not null
        )
        """,
    ),
    6: (
        """
        create table if not exists health_baseline (
            id integer primary key,
            file_path text not null unique,
            finding_count integer not null,
            created_at text not null
        )
        """,
    ),
    7: (
        """
        create table if not exists verification_runs (
            id integer primary key,
            finding_id text references findings(id) on delete cascade,
            command text not null,
            exit_code integer not null,
            output_summary text not null,
            created_at text not null
        )
        """,
    ),
}


def migrate(connection: sqlite3.Connection) -> None:
    for statement in BASE_TABLE_STATEMENTS:
        _ = connection.execute(statement)
    current_version = _current_schema_version(connection)
    for version in range(current_version + 1, SCHEMA_VERSION + 1):
        for statement in MIGRATION_STATEMENTS.get(version, ()):
            _ = connection.execute(statement)
    _ = connection.execute(f"pragma user_version = {SCHEMA_VERSION}")
    _ = connection.execute("delete from schema_version")
    _ = connection.execute(
        "insert into schema_version (version) values (?)",
        (SCHEMA_VERSION,),
    )


def _current_schema_version(connection: sqlite3.Connection) -> int:
    user_version_rows: list[tuple[int]] = connection.execute(
        "pragma user_version",
    ).fetchall()
    if user_version_rows and user_version_rows[0][0] > 0:
        return user_version_rows[0][0]

    schema_rows: list[tuple[int]] = connection.execute(
        "select version from schema_version order by version desc limit 1",
    ).fetchall()
    if schema_rows:
        return schema_rows[0][0]
    return 0
