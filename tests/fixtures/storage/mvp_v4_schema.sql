create table schema_version (version integer not null);

create table files (
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
);

create table symbols (
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
);

create table imports (
    id integer primary key,
    source_file_id integer not null references files(id) on delete cascade,
    imported_path text not null,
    imported_symbol text,
    resolved_file_id integer references files(id),
    confidence real not null
);

create table chunks (
    id integer primary key,
    file_id integer not null references files(id) on delete cascade,
    symbol_id integer references symbols(id) on delete set null,
    chunk_kind text not null,
    start_line integer not null,
    end_line integer not null,
    summary text,
    token_estimate integer not null default 0
);

create table symbol_references (
    id integer primary key,
    source_file_id integer not null references files(id) on delete cascade,
    source_symbol_id integer references symbols(id) on delete set null,
    target_file_id integer references files(id) on delete set null,
    target_symbol_id integer references symbols(id) on delete set null,
    reference_text text not null,
    start_line integer not null,
    end_line integer not null,
    confidence real not null
);

create table call_edges (
    id integer primary key,
    caller_symbol_id integer references symbols(id) on delete cascade,
    callee_symbol_id integer references symbols(id) on delete set null,
    source_file_id integer not null references files(id) on delete cascade,
    target_file_id integer references files(id) on delete set null,
    call_text text not null,
    start_line integer not null,
    confidence real not null
);

create table scan_runs (
    id text primary key,
    started_at text not null,
    completed_at text,
    index_version integer not null,
    rule_version text not null,
    files_scanned integer not null default 0,
    findings_created integer not null default 0,
    findings_resolved integer not null default 0,
    status text not null
);

create table findings (
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
);

create table finding_events (
    id integer primary key,
    finding_id text not null references findings(id) on delete cascade,
    event_type text not null,
    created_at text not null,
    details_json text not null
);

create table suggested_verifications (
    id integer primary key,
    finding_id text references findings(id) on delete cascade,
    command text not null,
    reason text not null,
    executes_in_v1 integer not null default 0
);

create table eval_runs (
    id text primary key,
    name text not null,
    started_at text not null,
    completed_at text,
    passed integer not null,
    score real not null,
    metrics_json text not null
);

create table frecency_signals (
    id integer primary key,
    path text not null,
    signal text not null,
    weight real not null,
    updated_at text not null
);

create table telemetry (
    id integer primary key,
    event_name text not null,
    created_at text not null,
    payload_json text not null
);

create table subjective_findings (
    id text primary key,
    provider text not null,
    prompt text not null,
    file_path text not null,
    title text not null,
    message text not null,
    confidence real not null,
    created_at text not null
);

insert into subjective_findings (
    id,
    provider,
    prompt,
    file_path,
    title,
    message,
    confidence,
    created_at
) values (
    'subjective-v4',
    'fake',
    'Explain the config layout.',
    'app.py',
    'Review config carefully',
    'Keep config small.',
    0.7,
    'now'
);

insert into schema_version (version) values (4);
pragma user_version = 4;
