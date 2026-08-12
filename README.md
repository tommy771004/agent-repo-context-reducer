<p align="center">
  <strong>Reduce before you read.</strong>
</p>

<p align="center">
  A deterministic repository context reducer for AI coding agents.
</p>

<p align="center">
  <a href="https://github.com/tommy771004/agent-repo-context-reducer/actions"><img src="https://github.com/tommy771004/agent-repo-context-reducer/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+"></a>
</p>

<p align="center">
  <a href="#installation">Install</a> &bull;
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#how-it-works">How It Works</a> &bull;
  <a href="#commands">Commands</a> &bull;
  <a href="#limitations">Limitations</a>
</p>

---

**Agent Repo Context Reducer** builds a compact structural map of a software repository **before** an AI agent reads full source files into its context.

It is designed for prompts like:

> Read this entire project and explain the architecture.

> Review this codebase and identify the important modules.

> Understand this repository before we refactor it.

Instead of encouraging the agent to read hundreds of files first and summarize later, the skill uses a local, deterministic Python scanner to extract structure, rank important files, and let the agent selectively open only the source it actually needs.

## What It Does

| Input | Reducer output |
|---|---|
| Repository tree | Directory counts and project map |
| Source files | Imports, classes, types, functions, exports and routes |
| Dependency manifests | Framework and ecosystem hints |
| Common entry files | Entry-point candidates |
| Large codebase | Ranked list of important files |
| Raw repository bytes | Approximate raw vs reduced context statistics |

The scanner does **not** use an LLM. It runs locally and emits JSON.

## Installation

This repository is an [Agent Skill](https://skills.sh/) and can be installed directly from GitHub.

### Install to a supported coding agent

```bash
npx skills add tommy771004/agent-repo-context-reducer
```

### Install globally

```bash
npx skills add tommy771004/agent-repo-context-reducer -g
```

### Claude Code

```bash
npx skills add tommy771004/agent-repo-context-reducer -g -a claude-code
```

### Codex

```bash
npx skills add tommy771004/agent-repo-context-reducer -g -a codex
```

### Cursor

```bash
npx skills add tommy771004/agent-repo-context-reducer -g -a cursor
```

### Multiple agents

```bash
npx skills add tommy771004/agent-repo-context-reducer -g \
  -a claude-code \
  -a codex \
  -a cursor
```

## Quick Start

You install the skill once, then ask your coding agent normally:

```text
Read this entire project and explain its architecture.
```

The skill instructs the agent to prefer this flow:

```text
Repository
    |
    v
Local deterministic scanner
    |
    v
Compact project map
    |
    v
AI agent reasoning
    |
    v
Selective full-file reads
```

instead of:

```text
Repository
    |
    v
Read every file into model context
    |
    v
Summarize afterward
```

For direct CLI use:

```bash
python scripts/repo_context.py scan . --pretty
```

Example:

```bash
python scripts/repo_context.py scan examples/sample-project --pretty
```

## How It Works

The reducer uses a three-level reading strategy.

### Level 1 — Project Map

First identify the shape of the repository:

- languages
- manifests
- framework hints
- entry points
- directory hot spots
- important-file candidates

No model call is required.

### Level 2 — Structural Context

For source files, the scanner extracts lightweight structure such as:

```text
src/services/order.ts
  imports:
    ./payment

  classes:
    OrderService

  functions:
    createOrder(input)
    cancelOrder(id)
```

The agent can use this map to decide where detailed reasoning should happen.

### Level 3 — Full Source

Only after the project map is available should the agent read full source files relevant to the task.

For example:

```text
User asks about checkout failures
        |
        v
repo-context scan .
        |
        +--> src/routes/order.ts
        +--> src/services/order.ts
        +--> src/services/payment.ts
        |
        v
Agent reads these files in full
```

The reducer is a **routing layer**, not a replacement for source-level reasoning.

## Why This Can Reduce Tokens

A model often needs to answer two different questions:

1. **Where should I look?**
2. **What does this code actually do?**

Reading every file in full answers both questions at maximum context cost.

This skill answers the first question with local code, then lets the model spend tokens only on the second question for a smaller set of files.

Important: token savings depend on the repository and the agent workflow. The tool does **not** claim a fixed reduction percentage or billing reduction.

The `stats` object uses a rough `UTF-8 bytes / 4` token estimate. This is useful for relative comparisons but is not a model tokenizer.

## Commands

### Scan a repository

```bash
python scripts/repo_context.py scan .
```

Pretty JSON:

```bash
python scripts/repo_context.py scan . --pretty
```

Save the result:

```bash
python scripts/repo_context.py scan . --pretty > /tmp/repo-context.json
```

Scan a subtree:

```bash
python scripts/repo_context.py scan src/services --pretty
```

Limit the scan:

```bash
python scripts/repo_context.py scan . \
  --max-files 2000 \
  --max-file-bytes 300000 \
  --pretty
```

### Inspect one file structurally

```bash
python scripts/repo_context.py inspect src/services/order.ts --pretty
```

### Version

```bash
python scripts/repo_context.py --version
```

## Example Output

```json
{
  "project": {
    "root_name": "sample-project",
    "files_scanned": 4,
    "languages": {
      "JavaScript": 3
    },
    "framework_hints": [
      "Express"
    ],
    "manifests": [
      "package.json"
    ]
  },
  "entry_points": [
    "src/index.js"
  ],
  "important_files": [
    "src/index.js",
    "src/services/order.js",
    "package.json"
  ],
  "files": [],
  "stats": {
    "estimated_raw_tokens": 0,
    "estimated_reduced_tokens": 0,
    "estimated_reduction_ratio": 0.0
  }
}
```

The real `files` array contains compact per-file structural summaries.

## Supported Source Types

The scanner currently recognizes common files from:

```text
Python
JavaScript / TypeScript
C#
Rust
Go
Java / Kotlin
Ruby
PHP
Swift
C / C++
Vue
Svelte
SQL
Shell
PowerShell
```

Symbol extraction is strongest on conventional formatting. It intentionally avoids heavyweight parser dependencies.

## What Gets Ignored

Common generated and dependency directories are skipped automatically, including:

```text
.git
node_modules
vendor
dist
build
target
bin
obj
coverage
.venv
__pycache__
.next
.nuxt
```

Large individual files are skipped according to `--max-file-bytes`.

## Agent Workflow

A recommended workflow for Claude Code, Codex, Cursor and similar coding agents:

```text
User prompt
   |
   v
Agent detects repository-wide analysis
   |
   v
Run repo-context scan
   |
   v
Read compact JSON map
   |
   +--> identify entry points
   +--> identify core modules
   +--> identify dependency boundaries
   +--> identify relevant hot spots
   |
   v
Read a small set of full source files
   |
   v
Reason and answer
```

The critical ordering rule is:

```text
Generate/scan -> Reduce -> Read -> Reason
```

not:

```text
Read everything -> Reduce -> Reason
```

Once raw source has already entered model context, this tool cannot recover those tokens.

## Output Contract

Top-level fields:

| Field | Meaning |
|---|---|
| `project` | Languages, manifests, framework hints and scan count |
| `entry_points` | Likely application entry files |
| `directories` | Highest-density scanned directories |
| `important_files` | Heuristic navigation ranking |
| `files` | Compact structural summaries |
| `stats` | Approximate context-size statistics |

Each source-file summary can include:

```text
path
language
bytes
lines
imports
classes
types
functions
exports
routes
importance
```

## Correctness Boundary

The reducer intentionally separates **data reduction** from **reasoning**.

It should determine:

```text
What files exist?
What symbols are visible?
What imports are declared?
Which files look structurally important?
```

The AI agent should determine:

```text
Is this architecture good?
Is this implementation correct?
Where is the bug?
Is there a security vulnerability?
What should be refactored?
```

That boundary is deliberate.

## Limitations

The source extractor is heuristic, not a compiler-grade AST.

It may miss or simplify:

- multiline signatures
- generated code
- macros
- metaprogramming
- dynamic imports
- framework-specific routing conventions
- deeply nested language syntax

The important-file score is a navigation heuristic, not a semantic importance proof.

For compiler-accurate analysis, a future version can add optional Tree-sitter or language-server adapters while keeping the default zero-dependency path.

## Repository Layout

```text
agent-repo-context-reducer/
├── SKILL.md
├── scripts/
│   └── repo_context.py
├── references/
│   └── design.md
├── examples/
│   └── sample-project/
├── tests/
│   └── test_repo_context.py
├── .github/
│   └── workflows/
│       └── test.yml
├── package.json
├── README.md
└── LICENSE
```

## Development

Requirements:

```text
Python 3.10+
```

No runtime packages are required.

Run tests:

```bash
python -m unittest discover -s tests -v
```

Run the demo:

```bash
python scripts/repo_context.py scan examples/sample-project --pretty
```

## Roadmap

Potential next steps:

- Tree-sitter adapters for precise multi-language parsing
- dependency graph output
- symbol-reference graph
- Git-aware changed-file prioritization
- test/build output reduction
- configurable importance rules
- framework-specific extractors
- incremental scan cache
- compact Markdown output mode
- optional findings reducer integration

## Philosophy

**Code should do deterministic reduction. Models should do reasoning.**

If an agent needs to understand a large repository, the expensive model should not have to read every byte just to discover which files matter.

Reduce first. Read selectively. Reason afterward.

## License

MIT
