<p align="center">
  <strong>Reduce before you read.</strong>
</p>

<p align="center">
  Task-aware repository navigation and context reduction for AI coding agents.
</p>

<p align="center">
  <a href="https://github.com/tommy771004/agent-repo-context-reducer/actions"><img src="https://github.com/tommy771004/agent-repo-context-reducer/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/runtime%20dependencies-0-brightgreen" alt="Zero runtime dependencies">
</p>

<p align="center">
  <a href="#installation">Install</a> &bull;
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#how-it-works">How It Works</a> &bull;
  <a href="#commands">Commands</a> &bull;
  <a href="#safety">Safety</a> &bull;
  <a href="#limitations">Limitations</a>
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
python scripts/repo_context.py map . --pretty
```

Or install the `repo-context` command from the repository:

```bash
python -m pip install git+https://github.com/tommy771004/agent-repo-context-reducer.git
repo-context --version
```

The runtime has no third-party Python dependencies.

## Quick Start

After installing the Skill, ask your agent normally:

```text
Read this entire project and explain its architecture.
```

The Skill tells the agent to start with:

```bash
python scripts/repo_context.py map <repo> --pretty
```

For a task-specific prompt:

```text
Find why payment succeeds but order status is sometimes not updated.
```

Prefer:

```bash
python scripts/repo_context.py query <repo> \
  "payment succeeds but order status is not updated" \
  --top-k 20 --pretty
```

Then inspect only the ranked files that are actually relevant.

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

## Incremental Cache

Structural summaries are cached in:

```text
.repo-context-cache/
```

Each entry is keyed by file path, modification time and size. Unchanged files do not need to be parsed again on the next scan.

The cache contains structural summaries, not full source text.

Disable it with:

```bash
repo-context map . --no-cache
```

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

Structural extraction currently recognizes:

- Python
- JavaScript / TypeScript / JSX / TSX
- C#
- Rust
- Go
- Java
- Kotlin
- Ruby
- PHP
- Swift
- C / C++
- Vue
- Svelte
- SQL
- shell / PowerShell

Python uses the standard-library AST. Other languages currently use lightweight language-aware extraction and fall back conservatively when syntax is ambiguous.

## Repository Layout

```text
agent-repo-context-reducer/
├── SKILL.md
├── README.md
├── SECURITY.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── pyproject.toml
├── repo_context/
│   ├── cli.py
│   ├── scanner.py
│   ├── parsers.py
│   ├── graph.py
│   ├── ranking.py
│   ├── git_utils.py
│   ├── workspaces.py
│   ├── cache.py
│   └── util.py
├── scripts/
│   └── repo_context.py
├── references/
│   └── architecture.md
├── examples/
│   └── sample-project/
└── tests/
    └── test_repo_context.py
```

## Development

Run the test suite:

```bash
python -m unittest discover -s tests -v
```

Run the sample project map:

```bash
python scripts/repo_context.py map examples/sample-project --pretty
```

Task-aware example:

```bash
python scripts/repo_context.py query examples/sample-project \
  "payment checkout" --top-k 5 --pretty
```

The repository intentionally keeps the runtime dependency-free so the Skill can work in coding-agent environments without a setup phase.

## Design Boundary

This project answers:

> Where should the agent look next?

It does **not** claim to answer:

> Is this implementation correct?

> Is this code secure?

> What business behavior was intended?

Those require reasoning over the selected full source, tests and runtime evidence.

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
