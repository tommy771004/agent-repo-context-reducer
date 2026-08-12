---
name: agent-repo-context-reducer
description: Prevent AI coding agents from blindly loading repository files. Build/sync a persistent graph index, route repository tasks to focused workflows, and generate token-budgeted context packs before full source reads.
---

# Agent Repo Context Reducer

Use this skill for repository understanding, debugging, code review, change-impact analysis, and other non-trivial codebase tasks.

## Core rule

**Index first. Query the graph before recursively reading source. Prefer symbol-level context over whole-file reads.**

The CLI is `repo-context` when installed. When it is not on PATH, run the bundled `scripts/repo_context.py` relative to this skill directory with Python 3.

## Mandatory entry workflow

1. Run `repo-context status <repo>`.
2. If no index exists, run `repo-context index <repo>`. Otherwise run `repo-context sync <repo>`.
3. Run `repo-context route "<user task>"`.
4. Read **only** the workflow and policy Markdown files returned by `route`. Do not load every reference file.
5. Run `repo-context context <repo> "<user task>" --budget 6000 --session <session-id>`.
6. Reason from that context pack first.
7. If more implementation detail is necessary, use `repo-context symbol`, `deps`, `impact`, or `admit` before a whole-file read.
8. Stop expanding context when the task is answerable. Treat `coverage` and `stop_condition` as heuristics, not proof.

## Read policy

Before a large/full source read, run:

`repo-context admit <repo> <file> "<user task>" --requested full`

If it returns `prefer-symbol` or `prefer-structure`, follow that recommendation unless the task genuinely requires full-file semantics.

## Graph semantics

The persistent graph represents resolved **static imports** and indexed symbol definitions. It is not a guaranteed runtime call graph. Dynamic dispatch, reflection, runtime dependency injection, generated code, and unresolved imports may be absent.

## Token semantics

Budgets use an approximate UTF-8-bytes/4 estimate. They are context-selection limits, not provider billing guarantees.

## Safety

Secret-like files, private keys, symlinks, large binaries, generated/minified output, VCS metadata, dependencies, and build directories are excluded by default. Do not override these guards merely to increase coverage.
