# PRD: Headroom-Inspired Context Optimization Features for Codebase MCP Server

## 1. Overview

This PRD defines a set of context optimization features to incorporate into the
codebase MCP server, inspired by the Headroom project.

Headroom is an open-source context compression layer for AI agents that
compresses tool outputs, logs, files, RAG chunks, and conversation history
before they reach the LLM. It supports library, proxy, wrapper, and MCP modes,
and exposes MCP tools for compression, retrieval, and stats. Its core ideas
include reversible compression, local storage of originals, content-type-aware
compression, token savings observability, and failure learning.

The codebase MCP server should **not become a generic compression proxy**. Its
primary value remains deterministic codebase intelligence for coding agents.
However, several Headroom-inspired ideas can make the server more efficient,
safer, and more useful when paired with Pi or other coding agents.

## 2. Product Goal

Improve the MCP server’s usefulness to AI coding agents by returning the
**smallest useful representation** of codebase data, while preserving exact
originals locally and allowing agents to retrieve detail only when needed.

The guiding principle:

> Summarize by default, preserve exact source data locally, retrieve exact
> detail on demand.

## 3. Non-Goals

The MCP server should not attempt to:

- Become a general-purpose LLM proxy.
- Replace Headroom’s generic compression layer.
- Compress all model traffic.
- Compress source code lossy when an agent is about to edit it.
- Route requests between LLM providers.
- Become dependent on Pi, Claude Code, Codex, or any single agent host.
- Require Headroom as a runtime dependency for core functionality.

Optional integration with Headroom may be considered later, but the MCP server
should remain useful without it.

## 4. Target Users

### Primary User

A developer using an AI coding agent against a local codebase who wants the
agent to:

- Read less irrelevant code.
- Avoid wasteful grep/search behavior.
- Use deterministic codebase intelligence.
- Make smaller and safer edits.
- Retrieve exact details only when necessary.
- Produce reliable verification reports.

### Primary Agent Consumer

An MCP-compatible coding agent such as Pi, Claude Code, Codex, Cursor, or a
custom harness.

## 5. Key Concepts Borrowed from Headroom

### 5.1 Reversible Context Compression

Headroom’s MCP server exposes `headroom_compress`, `headroom_retrieve`, and
`headroom_stats`. Compressed results include a hash that can be used to retrieve
the original content later.

The MCP server should borrow this pattern for large codebase results.

Instead of returning massive raw payloads, tools should return:

- A compact summary.
- The most relevant items.
- Counts of omitted items.
- A locally stored result ID.
- A retrieval path for the full original or filtered subsets.

### 5.2 Content-Type-Aware Result Shaping

Headroom routes different content types through different compression
strategies. Its README describes a pipeline involving cache alignment, content
routing, and compression/retrieval mechanisms.

The MCP server should use codebase-specific result shaping rather than generic
compression.

Examples:

- Symbol search results should be grouped by module, symbol type, and relevance.
- Test failures should be summarized by failing test, assertion, traceback root
  cause, and likely source files.
- Lint/type-check diagnostics should be grouped by file, severity, and
  autofixability.
- Smell reports should be ranked by severity, confidence, and refactor ROI.
- Large source files should be returned as outlines plus relevant ranges, not
  entire files by default.

### 5.3 Retrieval Over Truncation

Headroom’s value proposition is not merely shrinking text. It keeps originals
retrievable so information is not permanently lost. Its MCP docs state that
originals are stored locally and can be retrieved later by hash.

The MCP server should never silently discard important data. Large responses
should be summarized, but exact originals should remain available for follow-up
retrieval.

### 5.4 Token/Context Observability

Headroom exposes statistics around compression, retrieval, and token savings.

The MCP server should expose agent-facing context statistics so the developer
can evaluate whether the server is actually reducing token waste.

### 5.5 Failure Learning

Headroom includes a `headroom learn` workflow that mines failed agent sessions
and writes corrections to files such as `CLAUDE.md` or `AGENTS.md`.

The MCP server should eventually learn project-specific agent mistakes and
expose them as reusable guidance.

Examples:

- Correct test command.
- Correct Python executable or virtual environment command.
- Generated files that should not be edited.
- Integration tests that require Docker.
- Known flaky tests.
- Preferred project conventions.
- Common file location patterns.

## 6. Feature Set

## Feature 1: Standard Summarized Result Envelope

### Summary

All MCP tools that may return large results should use a consistent response
envelope.

### Problem

Raw MCP responses can become too large, forcing the model to reason over
irrelevant data. Existing tools may return large JSON arrays, logs, search
results, or diagnostic output with no explicit indication of what was omitted.

### Solution

Introduce a standard response envelope for summarized or partially returned
results.

### Proposed Shape

```json
{
  "kind": "symbol_search_result",
  "mode": "summarized",
  "summary": "Found 184 references to UserService. Returning the 20 most relevant results grouped by module.",
  "items": [],
  "omitted_count": 164,
  "original_result_id": "ctx_abc123",
  "retrieval_available": true,
  "retrieval_hints": [
    "retrieve_result(id='ctx_abc123')",
    "retrieve_result(id='ctx_abc123', query='tests only')",
    "retrieve_result(id='ctx_abc123', file='src/users/service.py')"
  ],
  "confidence": "high",
  "warnings": []
}
```

### Requirements

- Every large response must declare whether it is exact, summarized, sampled,
  truncated, or filtered.
- Summarized responses must include `original_result_id` when full retrieval is
  available.
- Summarized responses must include `omitted_count` when applicable.
- Summarized responses must include retrieval hints.
- Warnings must be explicit if the result is partial or heuristic.

### Acceptance Criteria

- Given a large symbol search result, the MCP server returns a compact envelope
  instead of an unbounded list.
- The response clearly states what was returned and what was omitted.
- The agent can retrieve the full result later using `original_result_id`.

---

## Feature 2: Local Result Store

### Summary

Store large raw MCP results locally and return stable result IDs for later
retrieval.

### Problem

Agents often need a compact summary first, but occasionally need exact details
later. Without a local result store, the server must either return everything
immediately or rerun expensive queries.

### Solution

Add a local result store backed by SQLite or the existing MCP server database.

### Stored Data

Each stored result should include:

- Result ID.
- Tool name.
- Query/input parameters.
- Raw full result.
- Summarized response.
- Created timestamp.
- Expiration timestamp, if applicable.
- Project/repo identifier.
- Content type.
- Approximate token count.
- Retrieval count.

### Result ID Format

Use a stable but opaque ID:

```text
ctx_<short_hash>
```

Example:

```text
ctx_a82f19c4
```

### Retention

Default retention:

- Session-scoped by default.
- Optional longer retention for debugging or evaluation.
- Configurable TTL.

### Requirements

- Store full raw results for summarized responses.
- Support result expiration.
- Support cleanup of expired results.
- Avoid storing sensitive data longer than configured.
- Never expose absolute sensitive paths unnecessarily in summaries if path
  redaction is enabled.

### Acceptance Criteria

- Large search results can be summarized and later retrieved.
- Expired results cannot be retrieved.
- The server reports a clear error when a result ID is unknown or expired.

---

## Feature 3: `retrieve_result`

### Summary

Expose an MCP tool to retrieve exact or filtered stored results.

### Problem

Agents need a way to drill down into summarized data without rerunning broad
searches or reading large files.

### Solution

Add a `retrieve_result` MCP tool.

### Tool Name

```text
retrieve_result
```

### Parameters

```json
{
  "result_id": "ctx_abc123",
  "query": "tests only",
  "file": "tests/test_users.py",
  "symbol": "UserService",
  "limit": 50,
  "mode": "exact"
}
```

### Modes

```text
exact
summary
filtered
sample
```

### Example Response

```json
{
  "kind": "retrieved_result",
  "result_id": "ctx_abc123",
  "mode": "filtered",
  "summary": "Returning 12 test-related references to UserService.",
  "items": [],
  "remaining_count": 0,
  "warnings": []
}
```

### Requirements

- Retrieve full exact data when requested.
- Support filtered retrieval by query, file, symbol, or result type.
- Support limits to prevent huge follow-up responses.
- Preserve exact snippets when source code is returned for editing.
- Clearly state when returned results are still partial.

### Acceptance Criteria

- An agent can retrieve only test-related results from a previous broad symbol
  search.
- An agent can retrieve all results for a specific file.
- An agent can retrieve exact source snippets when needed.

---

## Feature 4: Content-Type-Aware Response Shaping

### Summary

Shape MCP responses differently depending on the result type.

### Problem

Generic compression may lose important semantics. Codebase outputs need
domain-specific shaping.

### Solution

Implement result formatters for common codebase content types.

### Result Types

#### Symbol Search Results

Should be grouped by:

- Exact matches.
- Partial matches.
- Definition vs reference.
- File/module.
- Symbol type: function, class, method, variable, module.
- Relevance.

#### Source File Results

Should return:

- File outline.
- Imports.
- Public symbols.
- Relevant ranges.
- Warnings for generated or large files.
- Exact snippets only for relevant areas.

#### Test Output

Should return:

- Failed test names.
- Assertion summary.
- Traceback root cause.
- Relevant source files.
- Re-run command.
- Whether failure appears deterministic or environmental.

#### Lint Output

Should return:

- Diagnostics grouped by file.
- Autofixable vs manual.
- Severity.
- Suggested command.
- Changed-file relevance.

#### Type Check Output

Should return:

- Errors grouped by file.
- Error code/category.
- Public API type errors first.
- Likely root cause.
- Whether errors are pre-existing or introduced by recent changes, if known.

#### Smell Report

Should return:

- Finding type.
- Severity.
- Confidence.
- Refactor ROI.
- Risk level.
- Suggested next action.
- Relevant symbol/file.

#### Import Graph

Should return:

- Direct dependencies.
- Reverse dependencies.
- Cycles.
- High-centrality modules.
- Files affected by a potential edit.

### Requirements

- Do not use one generic summarizer for all content types.
- Preserve errors, warnings, failing assertions, and public API information.
- Prefer structured summaries over prose-only summaries.
- Include exact ranges when the agent may edit code.

### Acceptance Criteria

- Pytest output is summarized differently from symbol search output.
- Source code is never compressed into lossy prose when used for editing.
- Smell reports are ranked and actionable.

---

## Feature 5: Importance Preservation Rules

### Summary

Define rules for content that must never be dropped from summarized MCP
responses.

### Problem

Summarization and compression can hide critical information, making agents
overconfident.

### Solution

Add preservation rules for critical content.

### Always Preserve

- Errors.
- Tracebacks.
- Failing assertions.
- Security findings.
- Public API definitions.
- Changed files.
- Generated-file warnings.
- Highest-severity smell findings.
- Highest-complexity functions.
- Circular dependencies.
- Ambiguous or conflicting findings.
- Verification failures.
- User-provided constraints.
- Commands that failed.
- Files that could not be read.
- Permission errors.
- Environment errors.

### Requirements

- Every summarizer must run preservation logic before reducing content.
- Preserved items should be surfaced near the top of the response.
- If preserved items are too large, summarize them but keep exact retrieval
  available.

### Acceptance Criteria

- A large pytest output summary always includes failing assertions.
- A large lint output summary always includes errors before warnings.
- A large smell report always includes top-severity findings.

---

## Feature 6: Context and Token Stats

### Summary

Expose MCP server stats that help evaluate whether the server is reducing
context waste.

### Problem

The developer needs evidence that the MCP server improves agent performance and
reduces token usage.

### Solution

Add a `context_stats` MCP tool.

### Tool Name

```text
context_stats
```

### Example Response

```json
{
  "session_id": "sess_123",
  "tool_calls": 42,
  "summarized_results": 17,
  "retrievals": 5,
  "estimated_raw_tokens": 184000,
  "estimated_returned_tokens": 31000,
  "estimated_tokens_avoided": 153000,
  "largest_summarized_results": [
    {
      "tool": "symbol_search",
      "query": "UserService",
      "raw_tokens": 42000,
      "returned_tokens": 2100
    }
  ],
  "most_used_tools": ["repo_summary", "symbol_search", "related_tests"],
  "warnings": []
}
```

### Requirements

- Track MCP tool calls per session.
- Estimate raw token size and returned token size.
- Track retrievals.
- Track summarized vs exact responses.
- Track largest results.
- Track repeated queries.
- Expose stats through MCP.
- Avoid transmitting sensitive content in stats.

### Acceptance Criteria

- After a Pi session, the developer can inspect context savings.
- The stats show which MCP tools are most useful.
- The stats show when agents repeatedly retrieve overly broad data.

---

## Feature 7: Agent Session Event Log

### Summary

Capture lightweight event data for agent interactions with the MCP server.

### Problem

To improve the MCP server and future Pi profile, we need to observe where agents
succeed, fail, over-search, or ignore useful tools.

### Solution

Add an internal session event log.

### Event Types

```text
tool_called
large_result_summarized
result_retrieved
verification_suggested
verification_failed
verification_passed
agent_repeated_query
agent_requested_exact_large_result
server_warning_returned
```

### Event Shape

```json
{
  "event_type": "large_result_summarized",
  "timestamp": "2026-06-12T10:00:00Z",
  "session_id": "sess_123",
  "tool": "symbol_search",
  "raw_tokens": 42000,
  "returned_tokens": 2200,
  "result_id": "ctx_abc123"
}
```

### Requirements

- Events must be local-only by default.
- Events must not include full source code unless explicit debug mode is
  enabled.
- Events should power `context_stats`.
- Events should later power failure learning.

### Acceptance Criteria

- A session log can show how the agent used the MCP server.
- The log can identify repeated broad queries.
- The log can identify large exact retrievals.

---

## Feature 8: Failure Learning

### Summary

Mine failed agent/codebase sessions to generate project-specific agent guidance.

### Problem

Agents repeatedly make the same mistakes across sessions:

- Running the wrong test command.
- Guessing file paths.
- Editing generated files.
- Missing required environment setup.
- Running integration tests without Docker.
- Ignoring project-specific conventions.

Headroom’s `learn` feature mines failed sessions and writes corrections to agent
guidance files such as `CLAUDE.md` or `AGENTS.md`.

### Solution

Add a failure learning feature that analyzes MCP session event logs and
verification outcomes.

### Proposed Tool

```text
project_learnings
```

### Proposed CLI Command

```bash
codebase-mcp learn
```

### Example Output

```markdown
# Agent Project Learnings

- Use `uv run pytest`, not bare `pytest`.
- Tests for `src/billing/invoices.py` usually live in
  `tests/billing/test_invoices.py`.
- Do not edit files under `src/generated/`; edit the schema source instead.
- Full integration tests require Docker and should not be run unless explicitly
  requested.
- Prefer `ruff check --fix <changed-files>` for lint fixes.
```

### Requirements

- Identify repeated command failures.
- Identify path-guessing failures.
- Identify verification commands that eventually succeeded.
- Identify project-specific generated files or protected directories.
- Propose guidance entries.
- Do not automatically modify project files unless explicitly requested.
- Support export to `AGENTS.md`, `.cursorrules`, `CLAUDE.md`, or Pi-specific
  context files later.

### Acceptance Criteria

- After several sessions, the server can propose project-specific guidance.
- The developer can review guidance before writing it to disk.
- The guidance reduces repeated agent mistakes in later sessions.

---

## Feature 9: Project Guidance Store

### Summary

Store project-specific guidance learned from prior sessions and expose it to
agents.

### Problem

Even if the server learns project-specific rules, agents need a reliable way to
retrieve them at the start of a session.

### Solution

Add a project guidance store.

### Proposed Tool

```text
project_guidance
```

### Example Response

```json
{
  "project": "my-python-app",
  "guidance": [
    {
      "kind": "test_command",
      "text": "Use `uv run pytest`, not bare `pytest`.",
      "confidence": "high",
      "evidence_count": 7
    },
    {
      "kind": "protected_path",
      "text": "Do not edit files under `src/generated/`.",
      "confidence": "medium",
      "evidence_count": 3
    }
  ]
}
```

### Requirements

- Store guidance per project/repo.
- Include confidence and evidence count.
- Allow guidance to be manually accepted, rejected, or edited.
- Expose guidance at session start.
- Keep guidance local.

### Acceptance Criteria

- The agent can ask for project guidance before editing.
- Learned guidance persists across sessions.
- Incorrect guidance can be removed.

---

## Feature 10: Optional Headroom Integration

### Summary

Support optional integration with Headroom for generic compression workloads.

### Problem

The MCP server should focus on codebase intelligence, but some outputs may be
generic logs or long prose where Headroom could be useful.

### Solution

Add optional integration behind a feature flag.

### Config

```toml
[context_optimization]
headroom_enabled = false
headroom_mode = "mcp"
```

### Possible Integration Modes

```text
disabled
external_mcp
library
subprocess
```

### Requirements

- Headroom must not be required for normal server operation.
- Code-specific outputs should use native codebase-aware shaping first.
- Generic large logs may optionally be passed through Headroom.
- If Headroom fails, the server should fall back to native summarization.

### Acceptance Criteria

- The server works without Headroom installed.
- Enabling Headroom can compress generic large logs.
- Source-code edit context is not lossy-compressed through Headroom by default.

---

## 7. Recommended Implementation Phases

## Phase 1: Response Envelope and Result Store

### Features

- Standard summarized result envelope.
- Local result store.
- Result IDs.
- Basic retrieval.

### Deliverables

- Envelope schema.
- SQLite table or storage abstraction.
- `retrieve_result` MCP tool.
- Apply envelope to one high-volume tool, such as `symbol_search`.

### Success Criteria

- Large results are summarized and retrievable.
- Pi can ask for more detail without rerunning broad searches.

---

## Phase 2: Codebase-Specific Result Shaping

### Features

- Symbol search formatter.
- Source file formatter.
- Test output formatter.
- Lint/type-check formatter.
- Smell report formatter.

### Deliverables

- Result formatter abstraction.
- Preservation rules.
- Structured output formats per result type.

### Success Criteria

- Agents receive smaller, more actionable responses.
- Exact code is preserved when editing is likely.

---

## Phase 3: Context Stats and Session Events

### Features

- `context_stats` tool.
- Session event log.
- Token estimates.
- Largest-result tracking.
- Retrieval tracking.

### Deliverables

- Event schema.
- Stats aggregation.
- MCP stats endpoint/tool.

### Success Criteria

- Developer can evaluate the MCP server’s effect on token usage.
- Repeated broad queries and large retrievals are visible.

---

## Phase 4: Failure Learning

### Features

- Learn from failed commands and repeated mistakes.
- Generate project guidance.
- Reviewable guidance export.

### Deliverables

- `project_learnings` tool.
- `project_guidance` tool.
- Optional CLI command: `codebase-mcp learn`.
- Optional export to `AGENTS.md`.

### Success Criteria

- The server identifies repeated mistakes.
- Learned guidance improves future agent sessions.

---

## Phase 5: Optional Headroom Integration

### Features

- Optional Headroom compression for generic large outputs.
- Configurable integration mode.
- Fallback behavior.

### Deliverables

- Feature flag.
- Adapter interface.
- Tests for failure/fallback behavior.

### Success Criteria

- Headroom can be used when helpful.
- The MCP server remains independent and codebase-focused.

---

## 8. MCP Tool Additions

### New Tools

```text
retrieve_result
context_stats
project_guidance
project_learnings
record_agent_failure
record_successful_recovery
```

### Optional Tools

```text
compress_generic_output
retrieve_original_output
```

Only add optional compression tools if they do not distract from codebase
intelligence.

---

## 9. Data Model Sketch

### stored_results

```sql
CREATE TABLE stored_results (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  session_id TEXT,
  tool_name TEXT NOT NULL,
  input_json TEXT NOT NULL,
  raw_result_json TEXT NOT NULL,
  summary_json TEXT,
  content_type TEXT,
  raw_token_estimate INTEGER,
  returned_token_estimate INTEGER,
  created_at TEXT NOT NULL,
  expires_at TEXT,
  retrieval_count INTEGER DEFAULT 0
);
```

### session_events

```sql
CREATE TABLE session_events (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  tool_name TEXT,
  result_id TEXT,
  payload_json TEXT,
  created_at TEXT NOT NULL
);
```

### project_guidance

```sql
CREATE TABLE project_guidance (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  text TEXT NOT NULL,
  confidence TEXT NOT NULL,
  evidence_count INTEGER DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'proposed',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

---

## 10. Safety and Correctness Requirements

### Source Code Safety

- Do not lossy-compress source code intended for editing.
- Return exact source ranges when the agent may modify code.
- Mark generated files clearly.
- Mark partial results clearly.

### Privacy

- Store data locally only.
- Avoid telemetry by default.
- Make retention configurable.
- Allow result store cleanup.
- Avoid leaking sensitive full paths if path redaction is enabled.

### Agent Reliability

- Never silently omit critical errors.
- Always expose retrieval paths for summarized results.
- Include warnings for heuristic findings.
- Clearly distinguish exact, summarized, sampled, and partial data.

---

## 11. Success Metrics

### Quantitative

- Reduce average returned MCP response size by at least 50% for large
  search/report tools.
- Reduce repeated broad searches across a session.
- Increase ratio of targeted retrievals to full result dumps.
- Track estimated raw tokens avoided.
- Reduce repeated command failures after project guidance is adopted.

### Qualitative

- Pi uses MCP tools before raw search more often.
- Agent edits become smaller and more targeted.
- Agent final reports include better verification detail.
- Developer can understand what data was summarized and how to retrieve exact
  details.

---

## 12. Example Agent Flow

### Before

```text
Agent searches broadly.
Agent reads multiple large files.
Agent receives huge grep output.
Agent misses relevant tests.
Agent edits too broadly.
Agent runs wrong test command.
```

### After

```text
Agent calls repo_summary.
Agent calls symbol_search.
MCP returns summarized result with result_id.
Agent calls retrieve_result for relevant file/symbol only.
Agent calls related_tests.
Agent edits exact source range.
Agent calls verification_plan.
Agent runs targeted verification.
MCP records stats and learnings.
```

---

## 13. Open Questions

1. Should result storage be session-only by default, or should some results
   persist across sessions?
2. Should project guidance be exported to `AGENTS.md`, a Pi-specific context
   file, or both?
3. Should token estimation use a real tokenizer or a fast approximation?
4. Should Headroom integration be supported directly, or left as an external
   companion MCP server?
5. How aggressively should source file outlines omit private implementation
   details?
6. Should failure learning require explicit user approval before storing
   guidance?
7. Should result IDs be content-addressed hashes, random IDs, or both?

---

## 14. Recommended MVP Scope

The MVP should include only:

```text
1. Standard summarized result envelope
2. Local result store
3. retrieve_result tool
4. Content-type-aware shaping for symbol_search
5. Content-type-aware shaping for test output
6. Importance preservation rules
7. Basic context_stats
```

Do not implement failure learning or optional Headroom integration until after
real Pi sessions reveal repeated agent failures.

## 15. Final Recommendation

Incorporate Headroom’s best architectural ideas, but keep the MCP server focused
on codebase intelligence.

The most important features to borrow are:

```text
- reversible summarized responses
- result IDs
- filtered retrieval
- content-type-aware shaping
- preservation of critical information
- context/token stats
- failure learning from agent sessions
```

The MCP server should optimize for this behavior:

> Give the agent enough context to act safely now, preserve exact detail
> locally, and let the agent retrieve only what it needs next.
