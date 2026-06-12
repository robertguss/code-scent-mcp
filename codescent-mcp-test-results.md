# CodeScent MCP Test Results

Date: 2026-06-11

## Summary

The CodeScent MCP server passed source-read-only improvement-loop tests on both:

1. Fixture repo: `<repo>/tests/fixtures/python-basic`
2. Project repo: `<external:lx_data_lake>`

In both cases, the required CodeScent MCP sequence completed successfully, no source files were edited, and only `.codescent/` state was created or updated.

---

## Test 1: Fixture Repo

Target repo:

```text
<repo>/tests/fixtures/python-basic
```

### MCP tools called

1. `codescent_scan_code_health`
2. `codescent_get_next_improvement`
3. `codescent_get_finding_context`
4. `codescent_plan_refactor`
5. `codescent_suggest_tests`
6. `codescent_rescan`
7. `codescent_mark_finding`
8. `codescent_get_repo_status`

### Selected finding

- Finding ID: `python.deep_nesting:ba977cbdee86`
- Rule ID: `python.deep_nesting`
- File: `src/acme_tasks/oversized.py`

### Bounded context summary

- Deep nesting finding in `src/acme_tasks/oversized.py`
- Evidence: `depth`, `threshold`
- Relevant symbols included:
  - `acme_tasks.oversized.export_field_names`
  - `acme_tasks.oversized.load_export_rows`
  - `acme_tasks.oversized.save_export_rows`
  - `acme_tasks.oversized.render_export_rows`
  - `acme_tasks.oversized.build_export_rows`
  - `acme_tasks.oversized.summarize_export_rows`
  - `acme_tasks.oversized.calculate_nested_priority`
  - `acme_tasks.oversized.LegacyExportMapper`
  - `acme_tasks.oversized.LegacyExportMapper.keys`
- Relevant tests: none found
- Source ranges were bounded to small snippets around lines 102–107.

### Refactor plan non-goals

- Do not edit source files automatically.
- Do not change public behavior without tests.

### Suggested verification commands

```bash
pytest
```

### Rescan result

- Status: `complete`
- Scan ID: `0c0e56d2a03744c39a38fd7c42ca481d`
- Findings created: `13`
- Regressed finding IDs: `[]`
- Selected finding remained present: `python.deep_nesting:ba977cbdee86`

### Final mark_finding status

- Status: `open`
- Note: read-only MCP improvement loop completed; no source edits made.

### Source edit confirmation

`codescent_get_repo_status` reported:

- `read_only: true`
- `changed_files: []`
- `database_ok: true`
- `index_fresh: true`
- `indexed_files: 11`
- `git_available: false`
- `git_status: not_git`

Result: source files were not edited.

---

## Test 2: lx_data_lake Repo

Target repo:

```text
<external:lx_data_lake>
```

### MCP tools called

1. `codescent_scan_code_health`
2. `codescent_get_next_improvement`
3. `codescent_get_finding_context`
4. `codescent_plan_refactor`
5. `codescent_suggest_tests`
6. `codescent_rescan`
7. `codescent_mark_finding`
8. `codescent_get_repo_status`

### Selected finding

- Finding ID: `python.deep_nesting:16c2dccd9b83`
- Rule ID: `python.deep_nesting`
- File: `src/lx_data_lake/pipelines/populi_local/transforms.py`

### Bounded context summary

- Deep nesting finding in `src/lx_data_lake/pipelines/populi_local/transforms.py`
- Evidence: `depth`, `threshold`
- Relevant symbols included:
  - `lx_data_lake.pipelines.populi_local.transforms._quote_identifier`
  - `lx_data_lake.pipelines.populi_local.transforms._is_text_type`
  - `lx_data_lake.pipelines.populi_local.transforms._find_primary_key_column`
  - `lx_data_lake.pipelines.populi_local.transforms._is_temporal_column`
  - `lx_data_lake.pipelines.populi_local.transforms.get_silver_connection`
  - `lx_data_lake.pipelines.populi_local.transforms.get_gold_connection`
  - `lx_data_lake.pipelines.populi_local.transforms.bronze_to_silver`
  - `lx_data_lake.pipelines.populi_local.transforms.bronze_to_silver_all`
  - `lx_data_lake.pipelines.populi_local.transforms.silver_to_gold`
  - `lx_data_lake.pipelines.populi_local.transforms.run_all_transforms`
- Relevant tests identified:
  - `tests/pipelines/canvas_local/test_transforms.py`
  - `tests/pipelines/populi_local/test_transforms.py`
  - `tests/pipelines/watermark_local/test_transforms.py`
  - `tests/reports/test_reports.py`
  - `tests/test_pipeline_e2e.py`
- Source ranges were bounded to small snippets around helper functions in `transforms.py`.

### Refactor plan non-goals

- Do not edit source files automatically.
- Do not change public behavior without tests.

### Suggested verification commands

```bash
pytest tests/pipelines/canvas_local/test_transforms.py
pytest tests/pipelines/populi_local/test_transforms.py
pytest tests/pipelines/watermark_local/test_transforms.py
pytest tests/reports/test_reports.py
pytest tests/test_pipeline_e2e.py
```

### Rescan result

- Status: `complete`
- Scan ID: `81cc9d791e5f46558a7284ffc99dbca5`
- Findings created: `674`
- Regressed finding IDs: `[]`
- Selected finding remained present: `python.deep_nesting:16c2dccd9b83`

### Final mark_finding status

- Status: `open`
- Note: read-only MCP improvement loop completed on `lx_data_lake`; no source edits made.

### Source edit confirmation

`codescent_get_repo_status` reported:

- `read_only: true`
- `changed_files: []`
- `database_ok: true`
- `index_fresh: true`
- `indexed_files: 98`
- `finding_count: 733`
- `git_available: true`
- `git_status: dirty`

Result: source files were not edited by the MCP test. The repository was already dirty, but CodeScent reported no changed source files from the read-only loop.

---

## Final verdict

CodeScent MCP server passes the complete source-read-only improvement-loop test.
