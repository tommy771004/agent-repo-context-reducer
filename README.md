<p align="center">
  <strong>Reduce before you read.</strong>
</p>

<p align="center">
  Provider-aware repository context reduction and information orchestration for AI coding agents.
</p>

<p align="center">
  <a href="https://github.com/tommy771004/agent-repo-context-reducer/actions"><img src="https://github.com/tommy771004/agent-repo-context-reducer/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/runtime%20dependencies-0-brightgreen" alt="Zero runtime dependencies">
</p>

<p align="center">
  <a href="#short-reducer-commands">Shortcuts</a> &bull;
  <a href="#installation">Install</a> &bull;
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#how-it-works">How It Works</a> &bull;
  <a href="#commands">Commands</a> &bull;
  <a href="#safety">Safety</a> &bull;
  <a href="#design-boundary">Design Boundary</a>
</p>

<p align="center">
  <a href="README.md"><strong>English</strong></a> &bull;
  <a href="README.zh-TW.md">繁體中文</a>
</p>

---

**Agent Repo Context Reducer** helps Claude Code, Codex, Cursor, OpenCode and other coding agents understand a large repository **without reading every source file into model context first**.

It scans code locally, builds a lightweight dependency graph and symbol index, ranks files for the current task, and returns only the most useful structural context. The model can then selectively open full source where detailed reasoning is actually needed.

```text
Without reducer

User prompt
   |
   v
Agent reads hundreds/thousands of files
   |
   v
Large context wall
   |
   v
Reasoning


With reducer

User prompt
   |
   v
repo-context map/query
   |
   +-- Git-aware file index
   +-- Symbol extraction
   +-- Dependency graph
   +-- Task-aware ranking
   +-- Top-K context
   |
   v
Agent reads only relevant files in full
   |
   v
Reasoning
```

The reducer is **deterministic preprocessing**. It does not call an LLM.

## Two Product Surfaces

This repository deliberately exposes two separate surfaces:

1. **Core Reducer — default product surface.** Repository discovery, static index/graph, symbol extraction, provider reuse, context ranking, deduplication, session state and bounded context emission.
2. **Advisory Harness Planner — optional.** Complexity/risk/model-tier suggestions, lane budgets, dependency-aware schedules, quality-gate packets and bounded retry policy. These modules **do not spawn agents or switch models by themselves**. Execution requires the host or an external provider.

If your goal is only to reduce repository context, you can ignore the advisory harness commands entirely.

## What It Does

| Operation | What the reducer does |
|---|---|
| Repository discovery | Uses Git when available so `.gitignore` is respected |
| Project map | Detects languages, manifests, framework hints, entry points and workspaces |
| Source structure | Extracts imports, classes, types, functions, exports and routes |
| Python source | Uses the Python AST from the standard library |
| Other languages | Uses lightweight language-aware structural extraction |
| Dependency graph | Resolves local relative imports and reverse dependencies |
| Ranking | Combines entry points, graph centrality, structure and task keywords |
| Progressive context | Returns Top-K summaries instead of every scanned file |
| Changed mode | Finds Git changes and nearby affected files |
| Module mode | Narrows context to a subtree/workspace |
| Cache | Reuses unchanged structural summaries across scans |
| Safety | Skips secret-like paths, symlinks, generated code and oversized/binary files by default |

## Optional Advisory Harness Planner

The optional planner treats repository context as one part of a larger **information orchestration** problem. It does not hard-code Kimi, OpenHands, GraphRAG, or any other stack. Instead it resolves capabilities by layer and reuses a compatible trusted provider when one exists.

```text
User task
   |
   v
Task Complexity Router
   |
   +-- small task ------> single bounded worker
   |
   +-- larger task -----> dependency-aware schedule
                          |
                          +-- repository.*  -> code graph/index/search
                          +-- knowledge.*   -> docs/history/knowledge providers
                          +-- executor.*    -> external coding/autonomous agents
                          +-- orchestration.* -> multi-agent frameworks
                          +-- context.*     -> reducer budget/dedup/handoff/artifacts
                                               |
                                               v
                                         Minimal context
```

Key additions:

- **Deterministic-first Sorter** handles intent, complexity, risk, and capability routing in code with zero model calls by default; model escalation is considered only when deterministic routing is insufficient.
- **Vendor-neutral Model Tier Router** uses abstract `cheap`, `standard`, and `strong` tiers instead of hard-coding Claude, GPT, Kimi, Gemini, or any other vendor model.
- **Risk / Ambiguity Escalation** raises planner, worker, or grader tiers based on risk, blast radius, ambiguity, novelty, and cost of error.
- **Per-lane Budgeting** gives Planner/Worker/Tester/Grader child allocations that stay inside the existing task-wide budget.
- **Independent Quality Gate** grades reduced handoff/tests/evidence/risks instead of ingesting the worker's raw conversation.
- **Bounded Retry** caps reject loops, escalates tiers when justified, and falls back to human review after the attempt budget is exhausted.
- **Task Complexity Router** keeps trivial/focused work single-agent and only recommends multi-agent orchestration when the task crosses a complexity threshold.
- **Dependency-aware Scheduler** emits execution waves and only parallelizes independent stages.
- **Agent Handoff Reducer** strips raw subagent history down to decisions, evidence, targets, constraints, tests, risks and open questions.
- **Artifact Store** keeps large agent/tool outputs under `.repo-context/artifacts/` so the main model receives metadata or a reduced view first.
- **Knowledge Provider Layer** separates project memory from the native static code graph. The bundled fallback searches local docs/ADR text; it is explicitly **not GraphRAG**.
- **Executor Provider Layer** allows external coding/autonomous agents to be selected by capability. If no trusted provider exists, unsupported executor capabilities remain unresolved instead of pretending the reducer can execute them natively.

### Model tier routing and quality gate

```text
User task
   |
   v
Deterministic router (0 model calls)
   |
   +-- complexity
   +-- risk / ambiguity / novelty
   +-- required capabilities
   |
   v
Abstract model tier
   +-- cheap     -> high-frequency, low-risk bounded work
   +-- standard  -> normal implementation / reasoning
   +-- strong    -> high-risk, ambiguous, architectural, final grading
   |
   v
Dependency-aware lanes
   |
   v
Artifact + handoff reducer
   |
   v
Independent grader
   +-- PASS
   +-- RETRY (bounded)
   +-- HUMAN REVIEW
```

`cheap`, `standard`, and `strong` are abstract tiers, not model names. A concrete model is resolved only when the host or a registered provider exposes a compatible `model.*` capability. Otherwise model selection remains advisory/unresolved; the reducer does not pretend it can switch models.

The sorter does not use a cheap model by default because deterministic code is cheaper. A model is only a fallback when deterministic routing is insufficient and the host supports tier routing.

### Code graph vs. knowledge graph

These are intentionally different capabilities:

| Layer | Examples of content | Reducer behavior |
|---|---|---|
| `repository.graph` | files, imports, reverse imports, symbol definitions | native static fallback available |
| `knowledge.search` | README, docs, ADRs, architecture notes, changelog | native lexical fallback available |
| `knowledge.graph` | entities/decisions/history relationships | external provider only unless a real compatible implementation is installed |
| `executor.code` / `executor.autonomous` | coding/engineering execution | external provider only |

This avoids rebuilding a second graph merely because an external knowledge or code-graph provider is already installed.

Provider manifest templates are included under `examples/provider-layers/`. They intentionally omit executable commands: copy a template into `.repo-context/providers.d/`, add a real adapter for the installed tool, and trust it only after verifying the command contract.

## v1.4 Architecture Hardening

v1.4 focuses on audit-driven correctness and maintainability rather than adding another orchestration layer:

- project-scope host shortcuts are portable and never bake a developer-specific absolute path into committed files;
- committed Claude/Codex shortcut snapshots are generated from the same renderer and protected by drift tests;
- runtime state and structural cache live under one `.repo-context/` tree;
- `capabilities.json` is generated from runtime `NATIVE_CAPABILITIES` and checked in tests;
- `map` and `query` have distinct output contracts;
- `sync` is described truthfully as a cache-aware refresh: source parsing can be reused, while graph/ranking are rebuilt;
- CLI parsing, context orchestration and repository command handling are split into separate modules.

## Short Reducer Commands

The public interface is intentionally small. Humans use intent commands; the Skill chooses workflows; the shared runtime handles provider detection, reuse, fallback, graph/index, deduplication and budgets.

| Shortcut | Purpose | Internal routing |
|---|---|---|
| `/reducer-repo <task>` | General repository work | Automatic routing |
| `/reducer-debug <task>` | Debug a bug or failure | Forced `debug` workflow |
| `/reducer-impact <task>` | Analyze change impact | Forced `change-impact` workflow |
| `/reducer-review <task>` | Review code or changes | Forced `review` workflow |
| `/reducer-doctor` | Detect overlapping Skills/plugins/providers | Provider/capability doctor |

The shortcuts do **not** create separate indexes or graphs. They all call the same `repo-context` runtime and the same persistent state.

### Claude Code slash commands

Install the project-local shortcuts once:

```bash
repo-context host-install --host claude-code --scope project --repo .
```

Project-scope shortcuts intentionally contain the portable command `repo-context`, so every machine that uses committed project shortcuts must have the CLI on `PATH`. If you are running only from a source/Skill checkout and do not want to install the CLI, use a machine-local global shortcut instead:

```bash
python3 scripts/repo_context.py host-install --host claude-code --scope global --repo .
```

Then use, for example:

```text
/reducer-debug payment succeeds but order status stays pending
/reducer-impact I changed PaymentService; what can break?
/reducer-review review the current changes
```

Global install is also available with `--scope global`.

### Codex named Skills

Install the same facade names into the Codex Skill directory:

```bash
repo-context host-install --host codex --scope project --repo .
```

This creates `reducer-repo`, `reducer-debug`, `reducer-impact`, `reducer-review`, and `reducer-doctor` as named Skills. If the current Codex client exposes installed Skills through `@` mentions, you can use forms such as `@reducer-debug`; otherwise invoke/select the named Skill using the host's supported Skill UI.

Check installation:

```bash
repo-context host-status --host claude-code --scope project --repo .
repo-context host-status --host codex --scope project --repo .
```

The underlying stable facade API is also available for adapters:

```bash
repo-context run reducer-debug "payment succeeds but order status stays pending" --repo .
```

## Installation

### Agent Skill — recommended

Install directly from GitHub with the open Agent Skills CLI:

```bash
npx skills add tommy771004/agent-repo-context-reducer
```

Install globally:

```bash
npx skills add tommy771004/agent-repo-context-reducer -g
```

Claude Code:

```bash
npx skills add tommy771004/agent-repo-context-reducer -g -a claude-code
```

Codex:

```bash
npx skills add tommy771004/agent-repo-context-reducer -g -a codex
```

Cursor:

```bash
npx skills add tommy771004/agent-repo-context-reducer -g -a cursor
```

Multiple agents:

```bash
npx skills add tommy771004/agent-repo-context-reducer -g \
  -a claude-code \
  -a codex \
  -a cursor
```

### Python CLI — optional

Clone and run without installation:

```bash
git clone https://github.com/tommy771004/agent-repo-context-reducer.git
cd agent-repo-context-reducer
python3 scripts/repo_context.py map . --pretty
```

Or install the `repo-context` command from the repository:

```bash
python3 -m pip install git+https://github.com/tommy771004/agent-repo-context-reducer.git
repo-context --version
```

The runtime has no third-party Python dependencies.

**Distribution boundary:** `npx skills add` installs the Skill content (`SKILL.md`, references and bundled scripts). `pip`/`pipx` installs the Python runtime and `repo-context` console command. The wheel is intentionally a runtime distribution; it is not a replacement for installing the Skill documentation tree.

## Quick Start

After the host shortcuts are installed, use the intent facade instead of manually chaining low-level commands:

```text
/reducer-repo explain this project's architecture
/reducer-debug payment succeeds but order status is sometimes not updated
/reducer-impact I changed PaymentService; what can break?
/reducer-review review the current changes
```

The facade performs task/complexity routing, capability detection, provider reuse, native fallback where implemented, and bounded context planning through one shared runtime.

If the host does not expose slash/named-Skill shortcuts, call the stable facade API directly:

```bash
repo-context run reducer-debug \
  "payment succeeds but order status is not updated" \
  --repo . --pretty
```

Low-level `map`, `query`, `deps`, `symbol`, `knowledge`, `handoff`, and similar commands remain available for adapters and advanced workflows.

## How It Works

The core principle is **progressive disclosure of code context**.

### Level 0 — Index locally

The tool scans the repository without sending source to a model.

When Git is available, file enumeration uses Git so ignored files are not indexed. Otherwise it falls back to a guarded filesystem walk.

### Level 1 — Project map

```bash
repo-context map . --top-k 25
```

Returns:

- languages
- framework hints
- manifests
- workspaces / monorepo modules
- entry points
- directory hot spots
- graph-central files
- Top-K structural summaries

It intentionally does **not** return a summary for every file by default.

### Level 2 — Task-aware query

```bash
repo-context query . "authentication refresh token failure" --top-k 20
```

Ranking combines:

```text
static structure
+ entry-point distance
+ imported-by/imports centrality
+ filename/symbol/import/query matches
```

This is deterministic lexical ranking. No embedding or model call is used.

### Level 3 — Module / dependency drill-down

```bash
repo-context module . src/services --query "payment" --pretty
repo-context deps . src/services/payment.ts --depth 2 --pretty
```

The agent can inspect one logical area without reopening the whole project map.

### Level 4 — Full source only when necessary

```bash
repo-context inspect src/services/payment.ts --pretty
```

The structural map helps the agent decide whether a full source read is needed. Exact implementation reasoning still belongs to the coding agent.

## Commands

### `run` — short facade API

Host adapters call one stable facade command instead of exposing the low-level workflow:

```bash
repo-context run reducer-repo "understand this repository" --repo .
repo-context run reducer-debug "payment succeeds but order stays pending" --repo .
repo-context run reducer-impact "I changed PaymentService" --repo .
repo-context run reducer-review "review the current changes" --repo .
repo-context run reducer-doctor --repo .
```

List the available facades:

```bash
repo-context commands --pretty
```

### `host-install` / `host-status`

Install or inspect the human-facing shortcuts:

```bash
repo-context host-install --host claude-code --scope project --repo .
repo-context host-install --host codex --scope project --repo .
repo-context host-status --host claude-code --scope project --repo .
repo-context host-uninstall --host claude-code --scope project --repo .
```

`host-uninstall` is a dry run until you pass `--yes`. It only considers the five `reducer-*` names, never scans the target directory, and keeps any shortcut you edited after installation unless you add `--force`.

### `update` / `remove` — what the package manager cannot reach

Package-level installs already have their own lifecycle: `npx skills update|remove` manages the Skill package, and `pip` manages the `repo-context` console command. Neither of them knows about the slash-command files `host-install` writes, or about the `.repo-context/` state this runtime creates inside every repository it scans. That is what these two commands maintain.

```bash
# Refresh the persistent index and re-render already-installed shortcuts
repo-context update --repo . --target all --pretty

# Only re-render shortcuts (never installs where nothing was installed)
repo-context update --repo . --target shortcuts

# Print the package-manager commands for updating the distribution itself
repo-context update --target self
```

`--target self` **reports** the command to run and never executes it — this runtime has no third-party dependencies and does not shell out to package managers.

```bash
# Dry run: show what would be removed
repo-context remove --repo . --target state --pretty

# Apply it
repo-context remove --repo . --target state --yes
```

Removal is **dry run by default**, and `.repo-context/` is graded:

| Class | Contents | Removed by |
|---|---|---|
| Regenerable | `index.json`, `cache/`, `sessions/`, `runs/`, `budgets/`, `lifecycle/`, `provider-health.json`, `knowledge.json` | `--target state --yes` |
| User configuration and data | `config.json` (provider trust), `providers.json`, `providers.d/`, `artifacts/` | only with `--all` |

Anything unrecognized inside `.repo-context/` is reported and preserved rather than deleted. Other targets:

```bash
repo-context remove --repo . --target shortcuts --yes     # installed /reducer-* files
repo-context remove --repo . --target artifacts --yes     # stored agent/tool outputs
repo-context artifact remove <artifact-id> --repo .       # one artifact
```

The lower-level commands below remain available for runtime debugging, custom integrations and advanced workflows.

### Harness planning, handoff, artifacts and knowledge

These are runtime APIs used by advanced integrations; normal users can keep using `/reducer-*`.

```bash
# Decide whether multi-agent work is justified
repo-context complexity "refactor authentication across the repo" --pretty

# Resolve capabilities and build risk/model-tier/lane-budget/quality/retry policy
repo-context plan "refactor authentication across the repo" --repo . --context-budget 6000 --pretty

# Produce dependency-aware execution waves
repo-context schedule "implement OAuth across the app" --pretty

# Reduce a planner result before passing it to a coder
repo-context handoff planner implementer planner-result.json --repo . --store-artifact --pretty

# Build a reduced grader packet without forwarding the worker's raw conversation
repo-context quality packet "review payment change" worker-result.json --intent review --pretty

# Validate a grader JSON result
repo-context quality evaluate grader-result.json --risk-level high --pretty

# Apply the bounded retry / tier-escalation policy
repo-context retry-decision reject --attempt 1 --worker-tier standard --risk-level high --complexity-level complex --pretty

# Persist large outputs outside model context
repo-context artifact put research-result.json --repo . --producer researcher --pretty
repo-context artifact list --repo . --pretty

# Local docs/ADR memory fallback
repo-context knowledge index --repo . --pretty
repo-context knowledge search "why did we choose event queues?" --repo . --pretty
```

`plan` and `schedule` are advisory: the reducer does not silently spawn agents or invent a concrete model mapping for `cheap`/`standard`/`strong`. External model/executor/orchestrator providers must still be exposed through compatible manifests/adapters and pass the existing trust policy.

### `map`

Create a compact Top-K repository map:

```bash
repo-context map . --pretty
repo-context map . --top-k 15 --query "checkout payment" --pretty
```

`scan` is retained as a backward-compatible alias:

```bash
repo-context scan . --pretty
```

### `query`

Rank files for the current task:

```bash
repo-context query . "login sometimes fails after token refresh" --top-k 20 --pretty
```

### `module`

Focus on one subtree or monorepo module:

```bash
repo-context module . src/services --pretty
repo-context module . packages/auth --query "session" --pretty
```

### `deps`

Show dependency relationships:

```bash
repo-context deps . src/services/payment.ts --pretty
repo-context deps . src/services/payment.ts --depth 2 --pretty
```

Output includes:

- local imports
- imported-by files
- dependency neighborhood
- unresolved local imports

### `changed`

Use Git changes as the seed set and include nearby dependencies/callers:

```bash
repo-context changed . --pretty
```

Compare against a base branch/ref:

```bash
repo-context changed . --base main --depth 2 --pretty
```

This is useful after the agent has already made edits: it avoids rebuilding reasoning around unrelated parts of the repository.

### `inspect`

Extract structural information from one file:

```bash
repo-context inspect src/services/order.ts --pretty
```

### Common scan controls

```bash
repo-context map . \
  --top-k 25 \
  --max-files 10000 \
  --max-file-bytes 512000 \
  --pretty
```

Additional controls:

```text
--no-cache            Disable incremental structural-summary cache
--include-hidden      Include hidden files/directories where otherwise safe
--include-generated   Include files detected as generated
```

## Task-Aware Ranking

A globally important file is not always important for the current prompt.

For example:

```text
src/main.ts                    globally important
src/services/payment.ts        task important
src/models/order-status.ts     task important
```

With:

```bash
repo-context query . "payment completed order status" --top-k 10
```

query matches in paths, symbols and imports receive additional weight on top of dependency-graph signals.

This makes the reducer a navigation engine rather than only a source summarizer.

## Dependency Graph

Local relative imports are resolved against indexed source files when possible.

```text
src/index.js
    |
    v
src/routes/order.js
    |
    v
src/services/order.js
    |
    v
src/services/payment.js
```

The graph is used for:

- centrality ranking
- entry-point distance
- reverse dependency lookup
- changed-file impact neighborhoods
- task-aware file selection

External package imports are retained separately from local edges.

## Git-Aware Scanning

Inside a Git repository, the reducer prefers:

```bash
git ls-files --cached --others --exclude-standard
```

This means project `.gitignore` rules are respected automatically, including when scanning a subtree of the repository.

If Git is not installed or the directory is not a Git repository, it safely falls back to a filesystem walk with common build/cache/vendor directories excluded.

## Monorepo Support

The project map detects common workspace layouts from:

- `package.json` workspaces
- `pnpm-workspace.yaml`
- Cargo workspaces
- `apps/`
- `packages/`
- `services/`

Example:

```text
repo/
├── apps/web
├── apps/api
├── packages/auth
├── packages/ui
└── services/payment
```

Use `module` to narrow the context:

```bash
repo-context module . services/payment --pretty
```

## Persistent State and Cache

Commands that need the native repository index are **locally stateful by default**. On first write the reducer uses one state tree:

```text
.repo-context/
├── index.json
├── cache/summaries-v4.json
├── sessions/
├── runs/
├── budgets/
├── artifacts/
└── provider-health.json / providers.json / knowledge.json / ...
```

The first successful state write best-effort appends `.repo-context/` to the repository `.gitignore`. It also keeps the legacy `.repo-context-cache/` ignore entry for upgrades from pre-1.4 releases.

The summary cache is versioned. When the structural parsers change, the version is bumped and caches written by an earlier release are **discarded rather than migrated** — a summary produced by an older parser is stale by definition, and the cache key (path + mtime + size) would otherwise keep serving it for files that never changed. Stale cache files are removed on the next successful write.

`map`, `query`, `module`, `deps`, `callers`, `impact`, `changed`, `admit`, and `context` normally refresh/load the persistent index, so they can write `.repo-context/index.json` and cache metadata even though their **model-facing output is read-only repository analysis**.

`sync` is a **cache-aware refresh**, not a fully incremental graph update. Unchanged source summaries can be reused, but file enumeration, dependency graph construction, ranking and the persistent JSON write are rebuilt.

Use an already-existing index without refreshing it:

```bash
repo-context map . --no-sync
```

`--no-sync` never creates a missing index; run `repo-context index .` first. Disable structural-summary caching with:

```bash
repo-context map . --no-cache
```

The cache stores structural summaries, not full source text.

## Safety

The reducer is designed to scan repositories without blindly dumping sensitive or noisy content into agent context.

By default it skips:

- `.env` and `.env.*`
- filenames resembling `secret` / `credentials`
- private key and certificate key files (`.pem`, `.key`, `.p12`, `.pfx`, etc.)
- symlinks
- binary files
- oversized files
- generated/minified code
- common build/cache/vendor directories

`inspect` also refuses secret-like paths.

The tool does not attempt to print source contents in normal map/query/module/deps output.

See [SECURITY.md](SECURITY.md) for the trust model.

## Context Savings

The `map` output includes a rough comparison between source bytes considered and output JSON bytes.

Token estimates use:

```text
UTF-8 bytes / 4
```

This is intentionally only a relative approximation. It is **not** a tokenizer and **not** a billing estimate.

A small repository can produce little or no savings because metadata has overhead. The design targets medium and large codebases where selective reading matters.

The project does not claim a fixed token, latency or cost reduction percentage.

## Supported Languages

Extraction depth is **not uniform**. Language recognition (for the language census, indexing and ranking) is broader than structural extraction, and structural extraction is what feeds the dependency graph and symbol-level reading.

| Tier | Languages | Imports | Classes / types | Functions | `symbol` reading |
|---|---|---|---|---|---|
| Full AST | Python | yes | yes | yes | yes |
| Language-aware heuristic | JavaScript, TypeScript, JSX, TSX, Vue, Svelte, Rust, Go, C#, Java, Kotlin, C, C++, shell, PowerShell | yes | yes | yes | yes |
| Objects instead of imports | SQL | n/a | tables/views/types | procedures/functions | yes |
| Partial | Swift, PHP | **no** | yes | yes | yes |
| Partial | Ruby | **no** | yes | **no** | classes only |

Python uses the standard-library AST. Every other language uses regex-based, language-aware extraction that falls back conservatively when syntax is ambiguous.

**Import resolution details:**

- C/C++ `#include "local.h"` is treated as project-local and can resolve to a graph edge; `#include <system.h>` is kept as an external import. Declarations without a body are not reported as functions.
- shell `source ./lib.sh` and PowerShell `. .\helper.ps1` resolve to graph edges (backslash paths are normalized); `Import-Module Az` stays external.
- SQL has no import concept, so SQL files never produce dependency edges. `CREATE TABLE/VIEW/TYPE` become types and `CREATE PROCEDURE/FUNCTION` become functions.
- Swift, PHP and Ruby currently have no import extraction, so they contribute **no local dependency-graph edges**.

**What the lower tiers mean in practice:** every recognized file is discovered, respected by `.gitignore`, counted in the language census and ranked; but where imports are not extracted, ranking leans on path/filename signals rather than graph centrality. `repo-context symbol` can only read symbols that were extracted — when a symbol is missing it returns `Symbol not found` and progressive disclosure falls back to a full-file read.

## Repository Layout

The layout is grouped by responsibility instead of duplicating an exhaustive module list in documentation:

```text
agent-repo-context-reducer/
├── SKILL.md
├── capabilities.json              # generated from runtime capability source of truth
├── .claude/commands/              # generated/readable Claude shortcut snapshots
├── adapters/codex/                # generated/readable Codex Skill snapshots
├── repo_context/
│   ├── cli.py                     # thin dispatch / output / error boundary
│   ├── cli_parser.py              # argparse registration
│   ├── command_facade.py          # reducer-* single source of truth
│   ├── host_adapters.py           # host shortcut renderer/installer
│   ├── context_command.py         # context orchestration handler
│   ├── repository_commands.py     # map/query/deps/impact handlers
│   ├── scanner.py / parsers.py / symbols.py / graph.py / ranking.py
│   ├── indexer.py / index_runtime.py / storage.py / cache.py
│   ├── capabilities.py / delegate.py / provider_*.py / config.py
│   ├── context_planner.py / admission.py / ledger.py / lifecycle.py / voi.py
│   └── complexity.py / risk.py / model_router.py / scheduler.py / grader.py / ...
├── scripts/
│   ├── repo_context.py
│   └── generate_capabilities.py
├── references/
│   ├── overview.md
│   ├── architecture/
│   ├── workflows/
│   ├── policies/
│   ├── providers/
│   ├── harness/
│   ├── observability/
│   └── evaluation/
├── docs/audits/                   # architecture audit history/remediation evidence
├── examples/
├── .github/workflows/test.yml
└── tests/                         # reducer, harness, facade, manifest and version regressions
```

`repo_context/` remains dependency-acyclic; `cli.py` is no longer the home of parser registration or context/repository business logic.

## Development

Run the test suite:

```bash
python3 -m unittest discover -s tests -v
```

Run the sample project map:

```bash
python3 scripts/repo_context.py map examples/sample-project --pretty
```

Task-aware example:

```bash
python3 scripts/repo_context.py query examples/sample-project \
  "payment checkout" --top-k 5 --pretty
```

The repository intentionally keeps the runtime dependency-free so the Skill can work in coding-agent environments without a setup phase.

## Design Boundary

This project answers:

> Where should the agent look next?

> Should this task stay single-agent or expand into a dependency-aware workflow?

> What information should cross an agent handoff boundary?

> Which abstract model tier is justified by complexity/risk, and how much budget should each execution lane receive?

> Has an independent grader supplied enough evidence to pass the deterministic quality threshold, retry, or escalate?

It does **not** claim to answer:

> Is this implementation correct?

> Is this code secure?

> What business behavior was intended?

> Which concrete vendor model should `cheap` / `standard` / `strong` map to when the host exposes no such mapping?

Those require reasoning over the selected full source, tests and runtime evidence. The reducer also does not claim that an installed knowledge provider is equivalent to a code graph, or that an unresolved executor capability can be provided natively.

## Philosophy

```text
Discover with code.
Rank with code.
Reduce with code.
Reason with the model.
```

Do not spend expensive model context on repository navigation work that deterministic local tooling can do first.

## License

MIT
