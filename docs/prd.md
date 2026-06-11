# Product Requirements Document: Local Agentic Codebase Improvement Server

## 1. Working Title

TBD

Possible names:

- CodeScent
- RepoScent
- RefactorRadar
- SlopSleuth
- CodeTriage
- RepoDoctor
- Agentic Code Health
- Codebase Doctor
- ContextRefactor
- Code Steward

This PRD will refer to the project as **CodeScent** as a temporary working name.

## 2. Product Summary

CodeScent is a local, open-source, MCP-first codebase improvement server for AI
coding agents.

It gives agents structured codebase intelligence, fast search, deterministic
code-health findings, token-efficient context, refactor planning, and
verification guidance so they can improve a codebase without blindly grepping,
reading huge files, wasting tokens, or creating more AI-generated slop.

The product is not merely a linter, code search tool, repo map, or context
optimizer. It is a local agentic workflow layer for understanding, diagnosing,
improving, and verifying a codebase over time.

## 3. Core Thesis

AI coding agents are powerful, but they are still poor at careful codebase
discovery and long-term maintainability work.

They often:

- run broad greps across the repository;
- read large files into context unnecessarily;
- miss symbol relationships;
- overlook test coverage gaps;
- make isolated edits without understanding blast radius;
- generate duplicated or overcomplicated code;
- fix visible problems instead of high-leverage ones;
- lose progress after context compaction;
- lack a persistent code-health improvement workflow.

CodeScent exists to give agents the local knowledge and disciplined workflow
they need to behave more like careful engineers.

The goal is not to replace the LLM.

The goal is to make the LLM better informed, more efficient, more disciplined,
and safer when working in a codebase.

## 4. Goals

### 4.1 Product Goals

CodeScent should:

1. Provide an MCP-first interface for AI coding agents.
2. Build and maintain a local codebase index.
3. Expose structured code intelligence through agent-friendly tools.
4. Reduce unnecessary grep, find, and whole-file reads.
5. Provide fast, fuzzy, frecency-aware file and content search.
6. Detect deterministic code smells and refactor opportunities.
7. Identify likely AI slop and maintainability risks.
8. Give agents token-budgeted context for specific tasks.
9. Help agents understand impact, callers, references, related files, and
   relevant tests.
10. Maintain a persistent backlog of findings and improvement tasks.
11. Guide agents through safe, incremental refactor workflows.
12. Help verify changes through relevant checks and rescans.
13. Remain local-first, transparent, and open source.

### 4.2 User Goals

A developer using CodeScent should be able to ask an AI agent:

- “What are the highest-leverage refactors in this repo?”
- “Find the worst AI slop and fix one issue safely.”
- “Before editing this file, understand what calls it and what tests cover it.”
- “Give me only the context needed to refactor this component.”
- “What changed in this branch and what could break?”
- “What tests should we run for this change?”
- “What code smells remain after the last round of refactoring?”
- “Help improve this codebase over time without rewriting everything.”

### 4.3 Agent Goals

An AI coding agent should be able to:

- discover files and symbols without broad shell search;
- ask for compact context instead of reading everything;
- locate definitions, references, callers, callees, and related files;
- understand code-health findings with evidence;
- select the next best improvement task;
- receive a small, safe refactor plan;
- identify relevant tests and verification steps;
- update finding status after work is complete.

## 5. Non-Goals

CodeScent is not:

- a hosted SaaS product;
- a replacement for an IDE;
- a replacement for every linter or static analyzer;
- a generic MCP context-window optimizer;
- a general-purpose enterprise code search platform;
- a magic AI refactoring engine;
- a tool that rewrites whole repositories automatically;
- a cloud indexing service;
- a tool that sends source code to remote services by default;
- a replacement for human engineering judgment.

The product should start read-only or low-risk by default. Write-capable or
autofix features can come later.

## 6. Target Users

### 6.1 Primary Users

- Developers using AI coding agents heavily.
- Solo builders who want to keep AI-generated projects maintainable.
- Engineers working in unfamiliar codebases.
- Developers using MCP-compatible tools such as Claude Code, Codex, Cursor,
  Gemini CLI, OpenCode, or similar environments.
- Open-source maintainers who want agent-friendly codebase diagnostics.

### 6.2 Secondary Users

- Teams reviewing AI-generated pull requests.
- Developers managing technical debt.
- Educators teaching software design and refactoring.
- Agent tool authors who need structured repo context.
- CI maintainers who want code-health reports.

## 7. Prior Art and Inspiration

CodeScent should be an independent implementation, but it is openly inspired by
several projects and ideas.

### 7.1 Context Mode

Context Mode demonstrates the importance of context discipline: raw tool output
can flood the model’s context window, so agents need workflows that index,
search, summarize, and retrieve only relevant information.

CodeScent should adopt the same context-saving mindset, but focus specifically
on source-code intelligence, code health, refactoring, and verification.

### 7.2 CodeGraph

CodeGraph validates the value of a local, pre-indexed code knowledge graph for
AI coding agents. It strongly overlaps with the code-navigation side of
CodeScent.

CodeScent should learn from the idea of local semantic code intelligence, but
expand toward quality diagnosis, refactor prioritization, AI slop detection,
verification guidance, and persistent improvement workflows.

### 7.3 Desloppify

Desloppify validates the code-health and improvement-loop side of the idea:
scan, score, review, triage, execute, and rescan.

CodeScent should learn from this workflow while making the product MCP-first and
deeply connected to local symbol/context intelligence.

### 7.4 fff

`fff` demonstrates the value of very fast, fuzzy, typo-tolerant, frecency-aware
file and content search for humans and AI agents.

CodeScent should include a fast search layer inspired by this idea, especially
for file lookup, content lookup, changed-file search, fuzzy fallback, and
ranking results by agent usefulness.

### 7.5 Aider Repo Map

Aider’s repo map demonstrates the value of giving LLMs a concise, token-budgeted
map of repository symbols, files, and relationships.

CodeScent should extend this from a static repo-map artifact into an interactive
MCP-accessible context system.

### 7.6 Other Relevant Prior Art

CodeScent should also learn from:

- Tree-sitter-style parsing;
- ast-grep-style structural search;
- Semgrep-style static rules;
- Sourcegraph-style code intelligence;
- Sourcebot-style self-hosted code search;
- SCIP/LSIF-style code indexing;
- CodeQL-style code analysis;
- Zoekt-style fast code search;
- traditional linters, formatters, and complexity analyzers.

The product should not copy these tools. It should synthesize useful ideas into
an agent-native local codebase improvement workflow.

## 8. Product Principles

### 8.1 MCP-First

The main consumer is the AI coding agent.

The CLI exists for setup, debugging, inspection, and manual operation, but the
primary interface is MCP tools, resources, and prompts.

### 8.2 Local-First

Source code and indexes stay local by default.

No hosted service is required for core functionality.

### 8.3 Deterministic-First

Use deterministic analysis for facts:

- file paths;
- symbols;
- imports;
- references;
- callers;
- call relationships;
- file sizes;
- function sizes;
- complexity metrics;
- duplication candidates;
- test proximity;
- framework patterns.

Use LLMs only where judgment is actually needed, and clearly label subjective
analysis.

### 8.4 Token-Efficient by Design

Every MCP tool should return the smallest useful context by default.

Large source reads should be explicit, bounded, and justified.

### 8.5 Evidence-Based Findings

Every code-health finding must include evidence.

A finding should answer:

- what was found;
- where it was found;
- why it matters;
- how confident the tool is;
- what the agent should inspect next;
- what a safe improvement might look like.

### 8.6 Safe, Incremental Refactoring

The tool should push agents toward small, behavior-preserving improvements.

It should discourage sweeping rewrites unless explicitly requested.

### 8.7 Verification Is Required

Every improvement should include suggested verification:

- relevant tests;
- type checks;
- lint checks;
- build commands;
- characterization tests where needed;
- risk notes when verification is incomplete.

### 8.8 Human-Legible, Agent-Native

Outputs should be structured enough for agents and readable enough for humans.

### 8.9 Transparent and Extensible

Rules, scores, indexes, and findings should be inspectable.

The community should eventually be able to create language packs, framework
packs, custom rule packs, and architecture constraints.

## 9. Core Product Concepts

### 9.1 Repository Index

The repository index is a local representation of the codebase.

It should eventually include:

- files;
- directories;
- languages;
- file hashes;
- modification state;
- line counts;
- imports;
- exports;
- symbols;
- symbol signatures;
- classes;
- functions;
- methods;
- components;
- hooks;
- references;
- callers;
- callees;
- routes;
- tests;
- configuration files;
- dependency relationships;
- code chunks;
- summaries;
- findings;
- finding states;
- git state;
- frecency metadata.

### 9.2 Fast Search Layer

The fast search layer enables agent-friendly lookup when symbol-aware tools are
not enough.

It should support:

- file search;
- content search;
- fuzzy search;
- typo-tolerant matching;
- smart-case matching;
- changed-file search;
- test search;
- TODO/FIXME search;
- definition-biased search;
- frecency-aware ranking;
- result pagination;
- result scoring and explanations.

Search results should explain why they were ranked highly.

Example reasons:

- exact filename match;
- fuzzy filename match;
- symbol definition match;
- content match;
- recently modified;
- frequently accessed;
- test file;
- same module;
- related by import graph;
- part of current branch diff.

### 9.3 Code Intelligence Layer

The code intelligence layer answers structural questions.

It should support:

- repository map;
- symbol lookup;
- file context;
- symbol context;
- references;
- callers;
- callees;
- imports;
- exports;
- dependency graph;
- related files;
- relevant tests;
- route or entrypoint discovery;
- impact analysis.

### 9.4 Code Health Layer

The code health layer detects maintainability issues.

Initial categories:

- large files;
- large functions;
- large components;
- high complexity;
- deep nesting;
- too many imports;
- too many exports;
- too many parameters;
- duplicate code candidates;
- duplicate literals;
- TODO/FIXME/HACK clusters;
- dead code candidates;
- unused exports;
- missing nearby tests;
- weak test signals;
- framework-specific smells;
- architecture boundary violations;
- suspicious AI slop patterns.

### 9.5 Improvement Backlog

Findings should persist across scans.

Each finding should have a lifecycle:

- open;
- in_progress;
- resolved;
- deferred;
- wontfix;
- ignored;
- regressed;
- needs_review.

Findings should be grouped and ranked.

Ranking inputs may include:

- severity;
- confidence;
- file churn;
- git branch relevance;
- test gap;
- blast radius;
- complexity;
- duplication;
- proximity to changed files;
- estimated refactor size;
- safety of improvement;
- user-defined priority.

### 9.6 Refactor Planning

The tool should help the agent plan safe improvements.

A refactor plan should include:

- goal;
- non-goals;
- affected files;
- relevant symbols;
- risk level;
- proposed steps;
- recommended tests;
- fallback plan;
- expected behavior preservation;
- what not to change.

### 9.7 Verification Guidance

Verification should be connected to the code intelligence layer.

The tool should suggest:

- exact test files;
- likely missing tests;
- typecheck commands;
- lint commands;
- build commands;
- focused test commands;
- manual verification notes;
- characterization tests before risky refactors.

### 9.8 Session and Progress Awareness

The tool should remember:

- previous scans;
- current findings;
- resolved findings;
- deferred findings;
- recent agent work;
- changed files;
- verification status;
- code-health trends.

This does not need to become a full agent memory system in V1, but persistent
finding state is important.

## 10. Core MCP Capabilities

The exact names can change, but the MCP surface should eventually include tools
in these categories.

### 10.1 Repo Overview Tools

#### `get_repo_map`

Returns a compact overview of the repository.

Includes:

- detected languages;
- top-level structure;
- major directories;
- entrypoints;
- test directories;
- framework hints;
- dependency hints;
- current index freshness.

#### `get_repo_status`

Returns:

- index freshness;
- changed files;
- scan status;
- finding counts;
- database health;
- configured language packs;
- configured rules.

### 10.2 Search Tools

#### `search_files`

Searches file paths with fuzzy and frecency-aware ranking.

#### `search_content`

Searches content with ranked, bounded results.

#### `multi_search_content`

Runs multiple searches and merges/deduplicates results.

#### `search_changed_files`

Searches only modified, staged, or untracked files.

#### `search_todos`

Finds TODO/FIXME/HACK clusters.

#### `search_tests`

Finds likely test files for a query, symbol, file, or finding.

### 10.3 Code Intelligence Tools

#### `find_symbol`

Finds symbols by name, fuzzy name, or qualified path.

#### `get_symbol_context`

Returns signature, location, file, callers, callees, references, tests, and
relevant code ranges.

#### `get_file_context`

Returns a compact summary of a file without dumping the whole file.

#### `find_references`

Finds references to a symbol.

#### `find_callers`

Finds callers of a function, method, component, or symbol.

#### `find_callees`

Finds callees used by a function, method, component, or symbol.

#### `get_related_files`

Returns files related by imports, tests, routes, naming, directory proximity,
search similarity, or git history.

#### `get_impact`

Returns likely blast radius for changing a file or symbol.

### 10.4 Code Health Tools

#### `scan_code_health`

Runs enabled deterministic rules.

#### `get_smell_report`

Returns ranked findings.

#### `get_finding`

Returns one finding with evidence.

#### `get_finding_context`

Returns the smallest useful context to fix a specific finding.

#### `get_next_improvement`

Returns the highest-value next improvement based on configured priorities.

#### `explain_score`

Explains code-health scores and ranking decisions.

### 10.5 Workflow Tools

#### `plan_refactor`

Creates a safe, incremental refactor plan for a finding, file, or symbol.

#### `suggest_tests`

Suggests tests or checks relevant to a finding or change.

#### `verify_change`

Runs or recommends verification steps.

In early versions, this may only return suggested commands. Later versions may
execute commands with explicit permission.

#### `mark_finding`

Updates finding state.

#### `rescan`

Updates the index and reruns relevant checks.

### 10.6 Prompt Resources

The server should expose reusable prompts such as:

- refactor one finding safely;
- investigate a symbol before editing;
- add characterization tests;
- reduce large component size;
- review changed files for slop;
- verify a risky refactor;
- improve code health without broad rewrites.

## 11. CLI Requirements

The CLI is a companion interface.

Initial commands:

```bash
codescent init
codescent serve
codescent index
codescent scan
codescent status
codescent report
codescent doctor
codescent reset
```

Later commands:

```bash
codescent watch
codescent findings
codescent next
codescent explain <finding-id>
codescent export --format markdown
codescent config
codescent rules
```

The CLI should be useful for humans but should not be the primary agent
interface.

## 12. Data Requirements

The local data store should support:

- persistent indexing;
- incremental updates;
- fast lookups;
- finding state;
- search ranking metadata;
- git status snapshots;
- scan history;
- rule versions;
- schema migrations.

The data model should eventually support:

- files;
- symbols;
- symbol relationships;
- imports;
- references;
- call edges;
- chunks;
- tests;
- findings;
- rule definitions;
- finding evidence;
- finding state history;
- search history;
- frecency signals;
- git state;
- scan runs;
- verification runs.

Implementation details are intentionally deferred to architecture, but the
product requires a durable local index.

## 13. Configuration Requirements

A project should be configurable through a repository-local config file.

Configuration should include:

- include paths;
- exclude paths;
- generated/vendor/build directories;
- language packs;
- framework packs;
- rule enable/disable settings;
- severity thresholds;
- custom architecture rules;
- test command hints;
- typecheck command hints;
- lint command hints;
- build command hints;
- token budgets;
- privacy settings;
- optional LLM review settings.

Default exclusions should include common directories such as:

- `.git`;
- `node_modules`;
- `vendor`;
- `dist`;
- `build`;
- `.next`;
- `coverage`;
- generated lockfiles where appropriate;
- minified files;
- binary files;
- large generated artifacts.

## 14. Privacy and Security Requirements

### 14.1 Local-First

Core functionality must work locally without sending source code to a remote
service.

### 14.2 Read-Only by Default

The MCP server should be read-only by default.

Write-capable tools should be absent or disabled in early versions.

### 14.3 Repository Boundary

The server should not read files outside the configured repository root unless
explicitly configured.

### 14.4 No Network by Default

The server should not make network requests for core indexing or scanning.

### 14.5 Transparent Optional LLM Use

If LLM-assisted subjective review is added, it must be:

- opt-in;
- clearly labeled;
- configurable by provider;
- clear about what code/context is sent;
- skippable.

### 14.6 Safe Tool Descriptions

MCP tool descriptions should be written carefully to prevent misuse by agents.

They should tell agents:

- when to use the tool;
- when not to use the tool;
- expected input shape;
- whether source snippets may be returned;
- whether the tool is read-only;
- how to avoid large context output.

## 15. Reporting Requirements

Reports should be available in several formats:

- MCP structured results;
- markdown;
- JSON;
- terminal summary;
- optional HTML later.

Reports should include:

- summary;
- finding counts;
- top findings;
- severity distribution;
- confidence distribution;
- files with most issues;
- high-churn/high-risk areas;
- test gaps;
- suggested next improvements;
- verification recommendations.

Markdown reports should be designed for humans and LLMs.

JSON reports should be stable enough for automation.

## 16. Success Metrics

### 16.1 Agent Efficiency Metrics

Track or estimate:

- broad grep calls avoided;
- large file reads avoided;
- tokens avoided;
- number of targeted context requests;
- average context size per tool call;
- time to find relevant files;
- time to identify relevant tests.

### 16.2 Code Health Metrics

Track:

- open findings;
- resolved findings;
- findings by severity;
- findings by category;
- recurring findings;
- code-health trend across scans;
- files with repeated regressions;
- complexity trend;
- duplication trend;
- test-gap trend.

### 16.3 Workflow Metrics

Track:

- next improvement accepted;
- findings resolved per session;
- verification steps completed;
- findings marked deferred/wontfix;
- rescans after changes;
- regressions after resolution.

### 16.4 Adoption Metrics

For open-source adoption:

- successful installation;
- successful first index;
- successful first MCP connection;
- successful first scan;
- first finding resolved;
- number of supported agents;
- number of supported languages/frameworks;
- community rule packs.

## 17. MVP Definition

The MVP should prove the complete loop:

> index → search → scan → find one issue → gather context → plan safe refactor →
> verify → rescan

The MVP does not need broad language support or advanced subjective review.

### 17.1 MVP Language Scope

Start with one ecosystem.

Recommended starting point:

- TypeScript;
- JavaScript;
- TSX/JSX;
- React/Next.js-aware heuristics where easy.

This ecosystem is common among AI-generated projects and provides many obvious
code smell patterns.

Python-first MVP supersession, approved during planning on June 11, 2026:
the TypeScript/JavaScript/React starting point above is superseded for this
implementation milestone. The MVP now targets Python first, with other language
packs deferred until after the Python vertical loop is proven.

### 17.2 MVP MCP Tools

Required:

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

### 17.3 MVP CLI Commands

Required:

```bash
codescent init
codescent serve
codescent index
codescent scan
codescent status
codescent doctor
```

### 17.4 MVP Finding Types

Required:

- large file;
- large function;
- large React component;
- too many hooks;
- deep nesting;
- too many imports;
- TODO/FIXME/HACK cluster;
- duplicate literal strings;
- missing nearby test candidate;
- many responsibilities heuristic;
- changed file with no related tests;
- suspicious generated/slop pattern candidate.

### 17.5 MVP Search Features

Required:

- file path search;
- content search;
- result limits;
- fuzzy fallback;
- git-aware changed-file filtering;
- basic ranking explanation.

### 17.6 MVP Context Features

Required:

- file summary;
- symbol summary;
- imports/exports summary;
- caller/callee where confidently available;
- related files;
- relevant tests;
- bounded source ranges only when needed.

### 17.7 MVP Persistence

Required:

- local project database or equivalent local durable store;
- indexed file state;
- scan runs;
- findings;
- finding status;
- rule versions;
- basic rescan support.

## 18. Phased Roadmap

## Phase 0: Project Foundation and Product Lock

### Goal

Define the project clearly before implementation.

### Deliverables

- Final project name.
- README draft.
- CONTRIBUTING draft.
- LICENSE decision.
- Project brief.
- PRD.
- Prior art acknowledgements.
- Initial example workflows.
- Initial MCP tool list.
- Initial rule taxonomy.
- Initial glossary.

### Exit Criteria

- The project can be explained in one paragraph.
- The first implementation slice is clear.
- The project’s differentiation from Context Mode, CodeGraph, Desloppify, `fff`,
  and Aider is clear.

## Phase 1: Local Index and Basic MCP Server

### Goal

Create a working local MCP server with a minimal repository index.

### Deliverables

- Local project initialization.
- MCP server starts successfully.
- Repository root detection.
- Include/exclude handling.
- File inventory.
- Language detection.
- File hashing.
- Basic persistent index.
- `get_repo_map`.
- `get_repo_status`.
- `search_files`.
- `search_content`.
- CLI commands:
  - `init`;
  - `serve`;
  - `index`;
  - `status`;
  - `doctor`.

### Exit Criteria

- An MCP-capable agent can connect to the server.
- The agent can ask for repo structure.
- The agent can search files/content without using shell grep.
- Index freshness can be reported.

## Phase 2: Fast Search and Frecency Layer

### Goal

Make search fast, fuzzy, ranked, and agent-friendly.

### Deliverables

- Fuzzy file search.
- Smart-case matching.
- Fuzzy fallback for zero results.
- Result scoring.
- Ranking reasons.
- Basic frecency tracking.
- Git status annotations.
- Changed-file search.
- Search result pagination.
- Search exclusions for generated/vendor/build files.

### MCP Tools

- `search_files`
- `search_content`
- `multi_search_content`
- `search_changed_files`
- `search_todos`
- `search_tests`

### Exit Criteria

- The agent can find files and strings quickly with bounded output.
- Search results explain why they are relevant.
- Modified files are clearly marked.
- Fuzzy fallback prevents common agent search failures.

## Phase 3: Symbol and Code Intelligence MVP

### Goal

Give the agent structural understanding beyond text search.

### Deliverables

- Parser integration for TypeScript/JavaScript/TSX/JSX.
- Symbol extraction.
- Function/class/component detection.
- Import/export extraction.
- Basic reference extraction where reliable.
- Basic caller/callee extraction where reliable.
- File context summaries.
- Symbol context summaries.
- Related file detection.
- Test file matching heuristics.

### MCP Tools

- `find_symbol`
- `get_symbol_context`
- `get_file_context`
- `find_references`
- `find_callers`
- `find_callees`
- `get_related_files`

### Exit Criteria

- The agent can locate a symbol without grep.
- The agent can see imports, exports, callers, related files, and likely tests.
- The agent can ask for bounded context rather than whole files.

## Phase 4: Deterministic Code Health Scanner

### Goal

Detect obvious maintainability issues and AI slop candidates.

### Deliverables

- Rule engine.
- Rule configuration.
- Finding model.
- Finding evidence model.
- Finding severity/confidence.
- Scan runs.
- Markdown/JSON report export.
- Initial TypeScript/React rules.

### Initial Rules

- large file;
- large function;
- large component;
- too many hooks;
- too many props;
- deep nesting;
- too many imports;
- too many exports;
- TODO/FIXME/HACK cluster;
- duplicate literal strings;
- missing nearby test;
- changed source file without changed/related test;
- mixed responsibilities heuristic;
- route handler doing too much;
- suspicious generated code pattern.

### MCP Tools

- `scan_code_health`
- `get_smell_report`
- `get_finding`
- `explain_score`

### Exit Criteria

- The agent can ask for top code-health findings.
- Every finding includes evidence.
- Reports are useful to both humans and agents.
- The tool can identify at least one actionable improvement in a real repo.

## Phase 5: Finding Context and Refactor Planning

### Goal

Bridge code-health findings with code intelligence.

### Deliverables

- `get_finding_context`.
- Finding-to-symbol linking.
- Finding-to-related-files linking.
- Finding-to-tests linking.
- Risk notes.
- Safe refactor plan generation.
- Recommended verification steps.
- Token-budgeted context packs.

### MCP Tools

- `get_finding_context`
- `get_next_improvement`
- `plan_refactor`
- `suggest_tests`
- `get_impact`

### Exit Criteria

- Given a finding, the agent receives enough context to make a safe plan.
- The suggested plan is incremental and behavior-preserving.
- The agent is discouraged from reading unnecessary large files.
- Verification steps are included before the agent edits code.

## Phase 6: Persistent Improvement Workflow

### Goal

Turn findings into a durable backlog.

### Deliverables

- Finding lifecycle:
  - open;
  - in_progress;
  - resolved;
  - deferred;
  - wontfix;
  - ignored;
  - regressed.

- Status history.
- Rescan comparison.
- Resolved finding detection.
- Regressed finding detection.
- CLI backlog views.
- Agent workflow prompts.

### MCP Tools

- `mark_finding`
- `rescan`
- `get_backlog`
- `get_progress`
- `get_regressions`

### Exit Criteria

- The tool can track code-health improvement over multiple sessions.
- A finding can be resolved and remain resolved after rescan.
- Regressions are detectable.
- The agent can ask, “What should I improve next?”

## Phase 7: Verification and Risk Layer

### Goal

Help agents understand blast radius and verify changes.

### Deliverables

- Impact analysis for files/symbols/findings.
- Relevant test ranking.
- Suggested test commands.
- Suggested typecheck/lint/build commands.
- Verification run records.
- Risk scoring.
- Characterization test suggestions for risky areas.
- Branch/diff-aware risk reports.

### MCP Tools

- `get_impact`
- `suggest_tests`
- `verify_change`
- `review_diff_risk`
- `get_changed_file_health`

### Exit Criteria

- The agent can ask what could break before editing.
- The agent can receive a focused verification plan after editing.
- Risk reports are useful for PR review.

## Phase 8: Framework and Language Packs

### Goal

Expand beyond TypeScript/React with pluggable support.

### Deliverables

- Language pack interface.
- Framework pack interface.
- Rule pack interface.
- Custom rule configuration.
- Additional language support based on demand.

### Candidate Packs

- Next.js;
- React;
- Node/Express;
- Python;
- Go;
- Rust;
- Ruby/Rails;
- Phoenix/Elixir;
- Laravel/PHP.

### Exit Criteria

- Community contributors can add language/framework support without changing
  core internals.
- Rule packs can be enabled/disabled per project.

## Phase 9: Optional Subjective LLM Review

### Goal

Add opt-in subjective review for things deterministic analysis cannot judge
well.

### Possible Review Areas

- naming quality;
- abstraction quality;
- module boundaries;
- conceptual duplication;
- error-handling clarity;
- readability;
- overengineering;
- underengineering;
- architecture coherence.

### Requirements

- opt-in only;
- clear privacy notice;
- configurable model/provider;
- deterministic findings separated from subjective findings;
- subjective confidence clearly labeled;
- prompt templates inspectable.

### Exit Criteria

- Users can run subjective review safely and knowingly.
- Subjective findings never masquerade as deterministic facts.

## Phase 10: CI and PR Review Mode

### Goal

Bring code-health and risk analysis into pull requests.

### Deliverables

- CI command.
- PR/diff mode.
- Changed-file health scan.
- Risk report.
- Suggested tests.
- Markdown PR comment output.
- JSON output for automation.
- Failing thresholds.

### Exit Criteria

- A repository can run CodeScent in CI.
- A PR can receive a useful risk and code-health report.
- Teams can enforce or monitor quality gates.

## Phase 11: UI / Dashboard

### Goal

Make code-health progress visible to humans.

### Deliverables

- Local web dashboard.
- Finding list.
- Finding detail.
- Trend charts.
- Rule configuration view.
- Search/index status.
- Progress over time.
- Export controls.

### Exit Criteria

- A human can inspect project health without using an agent.
- The dashboard remains local-first.

## 19. MVP User Stories

### Story 1: Connect an Agent

As a developer, I want to start the local MCP server and connect it to my coding
agent so the agent can query repo intelligence directly.

Acceptance criteria:

- MCP server starts.
- Agent can list tools.
- Agent can call `get_repo_map`.
- Tool responses are bounded and readable.

### Story 2: Avoid Broad Grep

As an agent, I want to search files and content through CodeScent so I do not
need to run broad shell greps.

Acceptance criteria:

- Search results are limited.
- Results are ranked.
- Results include relevance reasons.
- Changed files are marked.

### Story 3: Find Symbol Context

As an agent, I want to find a symbol and its context so I can understand it
before editing.

Acceptance criteria:

- Symbol location is returned.
- Signature is returned where available.
- File context is returned.
- Related imports/exports are returned.
- Callers/callees are returned when known.
- Likely tests are returned when known.

### Story 4: Identify Code Smells

As a developer, I want the agent to identify high-priority maintainability
issues so we can improve code quality.

Acceptance criteria:

- Scan returns ranked findings.
- Findings include evidence.
- Findings include severity and confidence.
- Findings can be inspected individually.

### Story 5: Fix One Finding Safely

As an agent, I want to request context and a plan for one finding so I can make
a small behavior-preserving change.

Acceptance criteria:

- Finding context includes relevant files and symbols.
- Plan includes steps and non-goals.
- Plan includes verification recommendations.
- Plan discourages broad rewrites.

### Story 6: Track Progress

As a developer, I want resolved findings to stay resolved across rescans so I
can see improvement over time.

Acceptance criteria:

- Findings have persistent IDs.
- Findings can be marked resolved.
- Rescan updates finding state.
- Regressions can be detected.

## 20. Open Questions

These should be answered before architecture/spec work:

1. What is the final project name?
2. What license should the open-source project use?
3. What is the first supported language ecosystem?
4. Should V1 support only TypeScript/JavaScript or include Python as well?
5. Should the local index use SQLite from day one?
6. How much source code should MCP tools return by default?
7. What should the default token budget be for context packs?
8. Should the tool ever execute verification commands in V1, or only recommend
   them?
9. How should finding IDs remain stable across file edits?
10. Should subjective LLM review be postponed until after deterministic scanning
    is excellent?
11. What agent should be targeted first for installation docs?
12. Should the project include agent routing files like `AGENTS.md` /
    `CLAUDE.md` templates?
13. How should generated/vendor files be detected?
14. What are the first React/Next.js-specific smells to support?
15. Should the dashboard be postponed until after the MCP workflow is mature?

## 21. Recommended Decisions

To keep the project focused, the recommended initial decisions are:

1. Build MCP-first, not CLI-first.
2. Keep the server read-only in V1.
3. Use the CLI only for setup, indexing, scanning, status, and diagnostics.
4. Start with TypeScript/JavaScript/React/Next.js.
5. Use a durable local index from the beginning.
6. Prioritize deterministic analysis before subjective LLM review.
7. Prioritize one complete improvement loop over broad language support.
8. Include fast search early because agents need it immediately.
9. Include finding persistence early because the product is about improvement
   over time.
10. Defer CI, dashboard, and optional LLM review until the core MCP loop works.

## 22. First Build Milestone

The first build milestone should be:

> In a TypeScript/React repo, an MCP-connected agent can ask CodeScent for the
> top code-health finding, retrieve bounded context for that finding, receive a
> safe refactor plan, identify relevant tests, make the change using normal
> editing tools, and rescan to confirm the finding improved.

This milestone proves the product.

Everything else should build outward from that loop.

## 23. Long-Term Vision

CodeScent should become a local open-source operating layer for agentic software
engineering.

It should help AI coding agents work with discipline:

- search less blindly;
- read less wastefully;
- understand more structurally;
- refactor more safely;
- verify more consistently;
- improve codebases over time.

The long-term goal is not merely faster AI coding.

The goal is to make AI-assisted software development more maintainable, more
verifiable, and more trustworthy.
