# Architecture Document: Local Agentic Codebase Improvement Server

## 1. Purpose

This document defines the high-level architecture for a local, open-source,
MCP-first codebase improvement server for AI coding agents.

The system helps agents understand, search, diagnose, prioritize, refactor, and
verify a codebase without relying on broad grep, unnecessary whole-file reads,
or large context dumps.

The architecture should support the product vision described in the PRD:

> Index the codebase locally, expose structured intelligence through MCP, detect
> code-health issues, provide token-efficient context, guide safe refactors, and
> persist improvement progress over time.

## 2. Architectural Thesis

The product should be designed as a **local codebase intelligence and
improvement engine** with multiple interfaces.

The MCP server is the primary interface because the main user is the AI coding
agent.

The CLI is secondary and exists for humans to initialize, inspect, debug, and
manually operate the system.

The core engine must remain independent from MCP and CLI concerns so the product
can evolve without coupling business logic to any one interface.

## 3. High-Level Architecture

```text
AI Coding Agent / MCP Client
        |
        v
FastMCP Server Adapter
        |
        v
Application Service Layer
        |
        |-- RepoIndexService
        |-- SearchService
        |-- SymbolService
        |-- CodeHealthService
        |-- FindingService
        |-- RefactorPlanningService
        |-- VerificationService
        |-- ReportService
        |
        v
Core Engine
        |
        |-- File inventory
        |-- Parser adapters
        |-- Symbol extraction
        |-- Search index
        |-- Rule engine
        |-- Finding lifecycle
        |-- Git analysis
        |-- Context pack builder
        |
        v
Local Persistence
        |
        |-- SQLite database
        |-- In-memory hot indexes
        |-- Project config
        |-- Scan history
        |-- Finding state
        |
        v
Local Repository
```

## 4. Primary Architectural Principle

FastMCP should be used as the **MCP framework**, not as the application
architecture.

FastMCP is responsible for:

- exposing MCP tools;
- handling MCP protocol details;
- validating tool inputs and outputs;
- providing schemas to agents;
- managing MCP server lifecycle.

The project’s own core services are responsible for:

- indexing;
- searching;
- parsing;
- scanning;
- ranking findings;
- building context;
- planning refactors;
- suggesting verification;
- persisting state.

MCP tools should be thin wrappers around internal services.

Example:

```python
@mcp.tool
def get_smell_report(limit: int = 10):
    return code_health_service.get_smell_report(limit=limit)
```

Avoid placing large amounts of product logic directly inside MCP tool functions.

## 5. Public Interfaces

The system should expose three public surfaces over the same core engine.

```text
                  ┌──────────────┐
                  │ MCP / FastMCP │
                  └──────┬───────┘
                         │
┌──────────────┐         │         ┌────────────────┐
│ CLI          │─────────┼────────▶│ Core Services  │
└──────────────┘         │         └────────────────┘
┌──────────────┐         │                 │
│ Report Export│─────────┘                 ▼
└──────────────┘                    Local Index / DB
```

### 5.1 MCP Server

The MCP server is the primary agent interface.

It exposes tools such as:

- `get_repo_map`
- `get_repo_status`
- `search_files`
- `search_content`
- `find_symbol`
- `get_file_context`
- `get_symbol_context`
- `scan_code_health`
- `get_smell_report`
- `get_finding_context`
- `get_next_improvement`
- `plan_refactor`
- `suggest_tests`
- `mark_finding`
- `rescan`

### 5.2 CLI

The CLI is the human/admin interface.

Initial commands:

```bash
codescent init
codescent serve
codescent index
codescent scan
codescent status
codescent doctor
```

Later commands:

```bash
codescent findings
codescent next
codescent explain <finding-id>
codescent report
codescent reset
codescent config
```

### 5.3 Report Exporter

Reports should be generated from the same underlying services.

Supported formats over time:

- structured MCP output;
- JSON;
- Markdown;
- terminal summary;
- optional HTML later.

## 6. Recommended Initial Stack

### 6.1 Language

Use **Python** for the initial implementation.

Python is a good fit because the system is analysis-heavy, workflow-heavy, and
local-tooling-heavy.

It works well for:

- SQLite;
- filesystem walking;
- CLI development;
- parsing orchestration;
- rule engines;
- reporting;
- git integration;
- static-analysis experiments;
- fast iteration.

Performance-sensitive parts can later be moved to Rust or native extensions if
needed.

### 6.2 MCP Framework

Use **FastMCP** as the MCP server framework.

FastMCP should be used to expose the project’s internal capabilities as MCP
tools, resources, and prompts.

### 6.3 CLI Framework

Use a Python CLI framework such as Typer or Click.

The CLI should call the same application services used by MCP tools.

### 6.4 Persistence

Use a durable local project database from the beginning.

Recommended:

```text
.codescent/
  index.sqlite
  config.toml
  cache/
  logs/
```

SQLite should store durable project state.

In-memory indexes can be used for hot search paths and performance.

### 6.5 Parsing

Use parser adapters rather than hard-coding parsing logic into services.

Initial parser scope should target:

- TypeScript;
- JavaScript;
- TSX;
- JSX;
- React/Next.js heuristics.

Future parser adapters can support Python, Go, Rust, Ruby, Elixir, PHP, and
other languages.

Python-first MVP supersession, approved during planning on June 11, 2026: the
TypeScript/JavaScript/React starting point above is superseded for this
implementation milestone. The first parser adapter is the Python `ast` adapter;
other parser adapters remain post-MVP language packs.

### 6.6 Search

Use a two-layer search model:

```text
Persistent search data:
- files
- symbols
- content chunks
- findings
- git state
- frecency metadata

In-memory hot indexes:
- fuzzy file search
- content search cache
- recently changed files
- active-session ranking signals
```

Search should be inspired by fast, fuzzy, frecency-aware tools like `fff`, but
implemented inside this project’s own engine.

## 7. Core Services

## 7.1 RepoIndexService

Responsible for building and maintaining the local repository index.

Responsibilities:

- detect repository root;
- load project config;
- apply include/exclude rules;
- walk files;
- detect languages;
- hash files;
- detect changed files;
- store file inventory;
- trigger parsing;
- update index freshness;
- support full and incremental reindexing.

Inputs:

- repository path;
- config;
- file system state;
- git state.

Outputs:

- indexed files;
- index status;
- stale/fresh state;
- changed file list.

## 7.2 SearchService

Responsible for fast file and content lookup.

Responsibilities:

- path search;
- content search;
- fuzzy search;
- smart-case matching;
- fuzzy fallback;
- changed-file search;
- TODO/FIXME search;
- test search;
- result ranking;
- result explanations;
- pagination;
- frecency tracking.

Search results should include why they were ranked highly.

Example ranking reasons:

- exact filename match;
- fuzzy filename match;
- content match;
- symbol definition match;
- recently modified;
- frequently accessed;
- test file;
- related by directory;
- related by import graph;
- changed in current branch.

## 7.3 SymbolService

Responsible for structural code intelligence.

Responsibilities:

- extract symbols;
- find symbols;
- resolve symbol locations;
- summarize symbol context;
- track imports and exports;
- track references where possible;
- track callers and callees where possible;
- identify related files;
- identify likely tests;
- build bounded code context.

The SymbolService should not expose raw whole-file dumps by default.

## 7.4 CodeHealthService

Responsible for deterministic code-health scanning.

Responsibilities:

- run enabled rules;
- detect code smells;
- generate findings;
- assign severity;
- assign confidence;
- attach evidence;
- rank findings;
- explain scoring;
- produce reports.

Initial rules:

- large file;
- large function;
- large component;
- too many hooks;
- deep nesting;
- too many imports;
- too many exports;
- TODO/FIXME/HACK cluster;
- duplicate literal strings;
- missing nearby test;
- changed source file without related test;
- mixed responsibilities heuristic;
- suspicious generated/slop pattern.

## 7.5 FindingService

Responsible for persistent finding lifecycle.

Responsibilities:

- persist findings;
- generate stable finding IDs;
- compare findings across scans;
- mark findings open/in progress/resolved/deferred/wontfix/ignored;
- detect regressions;
- track history;
- retrieve next best improvement;
- group related findings.

Finding lifecycle:

```text
open
in_progress
resolved
deferred
wontfix
ignored
regressed
needs_review
```

## 7.6 RefactorPlanningService

Responsible for turning findings into safe improvement plans.

Responsibilities:

- gather finding context;
- identify affected files;
- identify related symbols;
- identify relevant tests;
- estimate risk;
- produce incremental plan;
- define non-goals;
- recommend verification;
- discourage broad rewrites.

A refactor plan should include:

- goal;
- risk level;
- affected files;
- relevant symbols;
- suggested steps;
- non-goals;
- verification plan;
- fallback guidance.

## 7.7 VerificationService

Responsible for verification guidance.

Early versions may only recommend commands.

Later versions may execute commands with explicit user permission.

Responsibilities:

- suggest relevant tests;
- suggest typecheck/lint/build commands;
- identify missing tests;
- suggest characterization tests;
- track verification status;
- connect verification to findings.

## 7.8 ReportService

Responsible for producing human-readable and machine-readable outputs.

Formats:

- structured objects for MCP;
- JSON;
- Markdown;
- terminal summaries;
- optional HTML later.

Reports should include:

- finding summary;
- top findings;
- evidence;
- risk notes;
- suggested improvements;
- verification guidance.

## 8. Core Engine Components

## 8.1 File Inventory

Tracks all included source files.

Stores:

- path;
- language;
- file hash;
- line count;
- size;
- modified time;
- git status;
- generated/vendor/build exclusion status;
- last indexed time.

## 8.2 Parser Adapters

Language-specific parsing should be isolated behind a common interface.

Each parser adapter should support as many of these as possible:

- symbols;
- imports;
- exports;
- references;
- functions;
- classes;
- methods;
- components;
- routes;
- tests.

Parser adapters should degrade gracefully.

If caller/callee extraction is not reliable for a language, the system should
return lower-confidence results rather than pretending certainty.

## 8.3 Rule Engine

Rules should be modular.

A rule should define:

- ID;
- name;
- description;
- category;
- severity default;
- confidence default;
- required inputs;
- detection logic;
- evidence schema;
- suggested action;
- whether it is language-specific;
- whether it is framework-specific.

Rules should be configurable.

## 8.4 Context Pack Builder

Responsible for building bounded, token-efficient context.

Inputs:

- file;
- symbol;
- finding;
- token budget;
- include source or summary only;
- requested detail level.

Outputs:

- summary;
- relevant files;
- relevant symbols;
- relevant tests;
- source ranges only where needed;
- risk notes;
- next recommended tool calls.

The default should favor summaries over raw source.

## 8.5 Git Analyzer

Responsible for git-aware context.

Responsibilities:

- detect changed files;
- detect staged/untracked files;
- identify recent churn;
- support branch/diff-aware scans;
- mark search results with git status;
- help rank findings by current branch relevance.

## 9. Local Persistence

The local project directory should look like:

```text
.codescent/
  index.sqlite
  config.toml
  cache/
  logs/
```

## 9.1 SQLite Responsibilities

SQLite should store:

- files;
- symbols;
- imports;
- references;
- call edges;
- chunks;
- findings;
- finding status;
- scan runs;
- rule versions;
- git snapshots;
- frecency signals;
- verification records.

## 9.2 In-Memory Responsibilities

In-memory indexes should support fast repeated queries during a server session.

Possible in-memory data:

- fuzzy path index;
- hot content index;
- active changed-file set;
- recent search cache;
- active session frecency.

## 10. Suggested Data Model

The exact schema should be finalized during implementation, but the system
likely needs these entities.

### 10.1 files

- id;
- path;
- language;
- hash;
- size_bytes;
- line_count;
- git_status;
- is_generated;
- is_test;
- last_indexed_at.

### 10.2 symbols

- id;
- file_id;
- name;
- qualified_name;
- kind;
- signature;
- start_line;
- end_line;
- exported;
- confidence.

### 10.3 imports

- id;
- source_file_id;
- imported_path;
- imported_symbol;
- resolved_file_id;
- confidence.

### 10.4 references

- id;
- symbol_id;
- file_id;
- start_line;
- end_line;
- reference_kind;
- confidence.

### 10.5 call_edges

- id;
- caller_symbol_id;
- callee_symbol_id;
- file_id;
- confidence.

### 10.6 chunks

- id;
- file_id;
- symbol_id;
- chunk_kind;
- start_line;
- end_line;
- summary;
- token_estimate.

### 10.7 findings

- id;
- stable_key;
- rule_id;
- file_id;
- symbol_id;
- severity;
- confidence;
- status;
- title;
- message;
- evidence_json;
- suggested_action;
- first_seen_scan_id;
- last_seen_scan_id;
- resolved_at.

### 10.8 scan_runs

- id;
- started_at;
- completed_at;
- index_version;
- rule_version;
- files_scanned;
- findings_created;
- findings_resolved;
- status.

### 10.9 verification_runs

- id;
- finding_id;
- command;
- status;
- started_at;
- completed_at;
- output_summary;
- exit_code.

## 11. MCP Tool Design Guidelines

Every MCP tool should be designed to reduce agent confusion and token waste.

Tool outputs should be:

- bounded by default;
- structured;
- ranked;
- evidence-based;
- explicit about confidence;
- clear about next steps;
- human-readable;
- safe.

MCP tool descriptions should instruct agents to use these tools before broad
shell search or large file reads.

Example guidance:

```text
Use this tool before running grep or reading large files. It returns ranked, bounded results with relevance reasons.
```

Source code should only be returned when:

- the agent explicitly requests it;
- the range is small;
- the context builder determines it is necessary;
- a token budget is provided.

## 12. Security and Privacy Architecture

## 12.1 Read-Only Default

Initial MCP tools should be read-only.

The server should not modify source files.

## 12.2 Repository Boundary

The server should only read files inside the configured repository root.

## 12.3 No Network by Default

Core indexing and scanning should not make network requests.

## 12.4 Optional Execution Later

Verification command execution should be postponed or permission-gated.

V1 can recommend commands without running them.

## 12.5 Optional LLM Review Later

Subjective LLM review should be opt-in, transparent, and separate from
deterministic scanning.

## 13. Configuration

A repository-local config file should control project behavior.

Example:

```toml
[project]
name = "my-app"

[index]
include = ["."]
exclude = [
  ".git",
  "node_modules",
  "dist",
  "build",
  ".next",
  "coverage"
]

[search]
default_limit = 20
fuzzy_fallback = true

[context]
default_token_budget = 3000
include_source_by_default = false

[rules]
enabled = true

[verification]
test_command = "npm test"
typecheck_command = "npm run typecheck"
lint_command = "npm run lint"
build_command = "npm run build"
```

## 14. Initial Implementation Roadmap

## Phase 1: Foundation

Build:

- Python project structure;
- FastMCP server;
- CLI skeleton;
- repository config;
- repository root detection;
- file inventory;
- SQLite setup;
- basic indexing;
- `get_repo_map`;
- `get_repo_status`.

Goal:

> An agent can connect to the MCP server and ask what is in the repo.

## Phase 2: Search

Build:

- file search;
- content search;
- fuzzy fallback;
- result limits;
- ranking reasons;
- git status annotations;
- changed-file search.

Goal:

> An agent can find files and strings without shell grep.

## Phase 3: Symbol Intelligence

Build:

- TypeScript/JavaScript/TSX/JSX parser adapter;
- symbol extraction;
- import/export extraction;
- basic file context;
- basic symbol context;
- related file detection;
- likely test file detection.

Goal:

> An agent can understand files and symbols without reading entire files.

## Phase 4: Code Health Scanner

Build:

- rule engine;
- initial smell rules;
- finding persistence;
- scan runs;
- smell report;
- finding detail;
- markdown/json report export.

Goal:

> An agent can ask for the highest-priority code-health issues.

## Phase 5: Finding Context and Refactor Planning

Build:

- finding-to-context mapping;
- next-best improvement;
- refactor plan generation;
- suggested tests;
- risk notes;
- mark finding status;
- rescan.

Goal:

> An agent can pick one finding, get minimal context, plan a safe refactor,
> verify, and rescan.

## Phase 6: Persistent Improvement Workflow

Build:

- finding lifecycle;
- scan comparison;
- regression detection;
- progress reporting;
- backlog view;
- agent prompt resources.

Goal:

> Code health can improve across multiple agent sessions.

## Phase 7: Verification and Diff Risk

Build:

- branch/diff awareness;
- changed-file health;
- impact analysis;
- verification command recommendations;
- verification run tracking;
- PR/report mode.

Goal:

> The tool can help agents and humans understand risk before and after changes.

## Phase 8: Extensibility

Build:

- language pack interface;
- framework pack interface;
- rule pack interface;
- custom rules;
- community documentation.

Goal:

> Other contributors can extend the system without changing the core engine.

## 15. Recommended Project Structure

Possible Python package structure:

```text
codescent/
  __init__.py

  mcp/
    server.py
    tools/
      repo.py
      search.py
      symbols.py
      health.py
      findings.py
      planning.py
      verification.py
    prompts.py
    resources.py

  cli/
    main.py
    commands/
      init.py
      serve.py
      index.py
      scan.py
      status.py
      doctor.py

  core/
    config.py
    paths.py
    models.py
    errors.py

  services/
    repo_index.py
    search.py
    symbols.py
    code_health.py
    findings.py
    refactor_planning.py
    verification.py
    reports.py

  engine/
    inventory.py
    parsers/
      base.py
      typescript.py
    rules/
      base.py
      large_file.py
      large_function.py
      large_component.py
      too_many_hooks.py
      todos.py
      missing_tests.py
    search/
      file_search.py
      content_search.py
      ranking.py
    context/
      context_pack.py
      token_budget.py
    git/
      status.py
      diff.py

  storage/
    db.py
    migrations/
    repositories/
      files.py
      symbols.py
      findings.py
      scans.py

  reports/
    markdown.py
    json.py

  tests/
```

## 16. Key Architectural Risks

### 16.1 Over-Coupling to MCP

Risk:

The whole application becomes FastMCP tool functions.

Mitigation:

Keep MCP thin. Put logic in services.

### 16.2 Overbuilding Too Early

Risk:

Trying to build code graph, search, smells, workflow, dashboard, CI, and
multi-language support at once.

Mitigation:

Build one complete loop first.

### 16.3 Poor Finding Stability

Risk:

Findings change IDs constantly after edits.

Mitigation:

Design stable finding keys using rule ID, path, symbol, and normalized evidence.

### 16.4 Stale Index

Risk:

Agent receives outdated code intelligence.

Mitigation:

Track file hashes, index freshness, and changed files. Warn when stale.

### 16.5 Too Much Context Returned

Risk:

The MCP server recreates the same context-window problem it is supposed to
solve.

Mitigation:

Bound outputs. Use token budgets. Prefer summaries. Require explicit source
range requests.

### 16.6 Unreliable Static Analysis

Risk:

Caller/callee/reference data may be incomplete.

Mitigation:

Return confidence. Degrade gracefully. Never imply certainty where there is
none.

### 16.7 Performance

Risk:

Python indexing/search may become slow on large repos.

Mitigation:

Incremental indexing, SQLite indexes, in-memory hot indexes, hashing, and future
Rust/native modules if needed.

## 17. First Milestone

The first real milestone should be:

> In a TypeScript/React repository, an MCP-connected agent can connect to
> CodeScent, get a repo map, search files/content, identify one high-priority
> smell, retrieve bounded context for that smell, receive a safe refactor plan,
> identify relevant tests, and rescan after the change.

This milestone proves the architecture.

Everything else should build outward from that loop.

## 18. Summary

The architecture should be:

- MCP-first;
- FastMCP-powered;
- Python-based initially;
- local-first;
- read-only by default;
- SQLite-backed;
- service-oriented;
- parser-adapter based;
- rule-engine based;
- token-budget aware;
- extensible over time.

The most important architectural decision is to separate the product’s core
engine from the MCP interface.

FastMCP should make the server easy to expose to agents.

The core engine should make the product valuable.
