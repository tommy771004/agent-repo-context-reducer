---
name: agent-repo-context-reducer
description: Build a compact structural map of a software repository before reading full source files. Use when asked to understand, review, explain, audit, or analyze an entire codebase or a large project. Prefer scan-first, then inspect only the files needed for reasoning.
---

# Agent Repo Context Reducer

Reduce repository context **before** it enters the model.

## When to use

Use this skill when the user asks to:

- understand an entire repository
- analyze project architecture
- review a large codebase
- explain how a project works
- find important modules or entry points
- inspect a project before debugging or refactoring
- compare architecture across many files

Do not start by reading every source file in full.

## Core workflow

1. Run a repository scan.
2. Read the generated project map.
3. Identify entry points, central modules, dependency manifests, and likely hot spots.
4. Inspect only the files needed to answer the user's question.
5. Read full source only when implementation details are necessary.

## Commands

From the installed skill directory:

```bash
python scripts/repo_context.py scan <repo-path> --pretty
```

For a smaller subtree:

```bash
python scripts/repo_context.py scan <repo-path>/src/services --pretty
```

To save the map:

```bash
python scripts/repo_context.py scan <repo-path> --pretty > /tmp/repo-context.json
```

## Output contract

The scanner returns JSON containing:

- project metadata
- detected languages
- framework/package hints
- dependency manifests
- entry-point candidates
- directory summary
- source-file summaries
- imports/dependencies
- class/function/type signatures
- important-file ranking
- estimated raw vs reduced context size

## Reasoning boundary

This tool is deterministic preprocessing. It should not:

- decide whether code is correct
- infer business intent that is not explicit
- replace detailed source inspection
- claim semantic equivalence between arbitrary code paths
- make security conclusions from signatures alone

The agent must perform reasoning after the reduction step.

## Context rule

Prefer:

```text
repository -> local scanner -> compact JSON -> agent reasoning -> selective source reads
```

Avoid:

```text
repository -> read every file into model context -> summarize afterward
```

Once tokens have already entered model context, the reducer cannot recover that cost.

## Escalation

After scanning, read full files when one of these is true:

- the user asks about implementation details
- a bug requires control-flow or state-flow reasoning
- a security finding depends on exact data handling
- generated structure is ambiguous
- a file is ranked important and directly related to the requested task

## Limitations

The structural extractor is intentionally lightweight and dependency-free. It uses language-aware heuristics rather than full compiler ASTs for most languages. Treat extracted symbols as a navigation aid, not a formal parser result.
