# Changelog

## 1.4.0

- Fixed project-scope host shortcuts so committed files use portable `repo-context` instead of developer-specific absolute Python/script paths.
- Removed the redundant root `commands/` snapshot; committed Claude/Codex shortcut snapshots are now renderer-generated and protected by drift tests.
- Consolidated persistent runtime state and structural cache under `.repo-context/`, with best-effort `.gitignore` management.
- Added structural extraction for C/C++ (`#include`, definitions), shell (`source`, both function forms), PowerShell (`Import-Module`, dot-sourcing, hyphenated names) and SQL (`CREATE TABLE/VIEW/TYPE/PROCEDURE/FUNCTION`). These languages previously contributed no imports, symbols or dependency-graph edges despite being listed as supported.
- Enabled `repo-context symbol` reading for C/C++, shell, PowerShell and SQL, so progressive disclosure no longer degrades to full-file reads for those languages.
- Registered `.bash` and `.zsh` as shell sources.
- Bumped the summary cache version and made stale-generation caches be discarded rather than migrated, so a parser change cannot keep serving summaries produced by the previous parser.
- Replaced the flat "Supported Languages" list in both READMEs with a per-language extraction tier table verified by regression tests.
- Made `--no-sync` strictly read an existing persistent index and fail when none exists.
- Corrected `sync` semantics: source parsing is cache-aware, while file enumeration, graph construction, ranking and index persistence are rebuilt.
- Generated `capabilities.json` from the runtime capability source of truth and added manifest consistency tests.
- Split `map` and `query` into distinct output contracts and removed avoidable ranking recomputation on non-query views.
- Split CLI parsing, repository handlers and context orchestration out of the former CLI god module.
- Renamed `references/architecture.md` to `references/overview.md` to avoid file/directory naming ambiguity.
- Reworked both READMEs around two explicit product surfaces: the Core Reducer and the optional advisory Harness Planner.
- Archived the v1.3 architecture audit and added a v1.4 remediation record under `docs/audits/`.

## 1.3.0

- Added deterministic risk/ambiguity routing and vendor-neutral `cheap` / `standard` / `strong` model tiers.
- Kept the sorter deterministic-first (zero model calls) and escalates only when needed.
- Added per-lane child budgets that remain bounded by the existing task-wide budget.
- Added an independent reduced-evidence quality gate with risk-aware thresholds.
- Added bounded retry/tier-escalation policy with human-review fallback.
- Integrated model/risk/lane/grade/retry planning into `plan`, `context`, and `/reducer-*` facades.
- Added advanced `quality` and `retry-decision` runtime APIs.

## 1.2.0

- Added heuristic Task Complexity Router to avoid unnecessary multi-agent fan-out for small tasks.
- Added dependency-aware agent scheduling with explicit execution waves; only independent stages are parallelizable.
- Added deterministic Agent Handoff Reducer for bounded planner/coder/reviewer handoffs.
- Added Artifact Store under `.repo-context/artifacts/` so large agent/tool outputs can persist outside model context.
- Added layered capability namespaces for `knowledge.*`, `executor.*`, `orchestration.*`, and `context.*`.
- Added local documentation/ADR knowledge fallback with deterministic lexical retrieval; it is explicitly not a semantic GraphRAG replacement.
- Added provider-aware Harness Planner that reuses trusted external providers and leaves unsupported optional executor capabilities unresolved rather than pretending native support.
- Fixed capability resolution so unsupported capabilities return `selected: null` instead of an empty native provider.
- Added `complexity`, `plan`, `schedule`, `handoff`, `artifact`, and `knowledge` runtime commands.
- Added orchestration metadata to context packs without automatically spawning agents.
- Expanded tests for complexity, handoffs, artifacts, knowledge fallback, scheduler dependencies, and unsupported executor capabilities.

## 1.1.0

- Added five human-facing reducer intent facades: `reducer-repo`, `reducer-debug`, `reducer-impact`, `reducer-review`, and `reducer-doctor`.
- Added Claude Code `/reducer-*` command adapter generation.
- Added Codex named-skill adapter generation with conditional `@reducer-*` usage when supported by the client.
- Added `repo-context run`, `commands`, `host-install`, and `host-status`.
- Facades share one provider registry, persistent graph/index, session ledger, budget and trace; they do not create duplicate repository state.
- Added explicit workflow forcing for debug, change-impact, and review facades.
- Simplified the root Skill so normal use goes through one facade instead of a manual `status → index → route → context` sequence.
- Added shortcut/adapter tests.

## 0.2.0

- Progressive Top-K output instead of emitting every file summary by default.
- Task-aware `query` ranking.
- Local import/dependency graph and reverse dependencies.
- Entry-point distance and graph centrality ranking signals.
- Git-aware file discovery with `.gitignore` support.
- `changed` mode for Git changes and affected dependency neighborhoods.
- `module` and `deps` drill-down commands.
- Python AST structural parser plus improved multi-line/language-aware heuristics.
- Monorepo/workspace detection.
- Incremental structural-summary cache.
- Secret, symlink, generated, binary and oversized-file guards.
- Optional installable `repo-context` Python CLI.
- Expanded cross-platform tests and documentation.

## 0.1.0

- Initial repository structural scanner and Agent Skill.
