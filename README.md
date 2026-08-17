# Agent Repo Context Reducer

**Reduce before reading.** Provider-aware repository context reduction, progressive reading, deterministic agent handoffs, and safe multi-worker fan-in for AI coding agents.

Version **1.5.0** · Python **3.10+** · **zero runtime dependencies**

[English](README.md) · [繁體中文](README.zh-TW.md)

## Why

Large coding agents often pay twice for context: first by reading too much source, then by concatenating every sub-agent result into the final model. This project reduces both boundaries with deterministic code before model reasoning begins.

```text
User Task
  -> route / risk / complexity
  -> repository index + graph + symbols
  -> ranking + value-of-information + budget
  -> minimal context
  -> parallel workers
  -> reduced handoffs
  -> fan-in reducer
  -> bounded synthesis packet
  -> final agent / grader
```

## Core features

- Git-aware repository discovery and `.gitignore` support.
- Static import graph, reverse dependencies, workspaces, entry points and symbols.
- Python AST plus conservative language-aware extraction for JS/TS, C/C++, shell, PowerShell, SQL and more.
- Task-aware file ranking and symbol-level progressive disclosure.
- Session dedup and delta context for changed symbols.
- Persistent `.repo-context/` state, artifact store and provider registry.
- Provider-aware capability resolution with native fallback.
- Deterministic task/risk/model-tier/schedule/budget planning.
- Bounded handoff reducer.
- v1.5 deterministic multi-worker fan-in, contradiction surfacing and synthesis packet budgeting.

## Install

```bash
python3 -m pip install .
repo-context --version
repo-context-fan-in --help
```

Or run directly:

```bash
python3 scripts/repo_context.py map . --top-k 25 --pretty
```

## Repository context

```bash
repo-context query . "payment checkout" --top-k 20 --pretty
repo-context context . "debug payment status pending" --budget 6000 --session payment-debug --pretty
repo-context symbol . src/services/payment.py charge --session payment-debug --pretty
```

The runtime follows progressive disclosure: structural summaries first, then high-value symbols, then full/delta source only when needed.

## v1.5 Fan-In

```bash
repo-context-fan-in examples/fan-in/worker-outputs.json \
  --max-estimated-tokens 1800 \
  --pretty
```

Fan-in performs validation, exact/canonical grouping, agreement metadata, structured contradiction detection and confidence ordering before producing a synthesis packet.

`canonicalKey` identifies a fact, not necessarily one asserted side. If two workers say `async` and another says `sync`, the reducer reports agreement `2 vs 1` and preserves the contradiction; it never reports all three as agreement.

Fuzzy semantic merge is disabled by default. A false merge can destroy evidence, while a missed duplicate only costs context.

## Synthesis budget

Contradictions are mandatory evidence. If they exceed the requested packet budget, the packet reports `budget.overflow = true` instead of deleting them to manufacture a successful reduction ratio.

## Provider model

Capabilities are namespaced (`repository.*`, `context.*`, `knowledge.*`, `executor.*`, `model.*`, `quality.*`). Trusted compatible providers may be reused. Unsupported execution/model capabilities remain unresolved instead of being faked by a native implementation.

## Harness planner

The optional planner returns deterministic recommendations for complexity, risk, abstract model tiers, dependency waves, lane budgets, quality gates and bounded retries. It does not spawn agents or choose vendor models by itself.

## Host facades

```bash
repo-context host-install --host claude-code --scope project --repo .
repo-context host-install --host codex --scope project --repo .
```

Facades: `reducer-repo`, `reducer-debug`, `reducer-impact`, `reducer-review`, `reducer-doctor`.

## Benchmark

```bash
repo-context benchmark examples/benchmark-tasks.json examples/sample-project --budget 1800 --pretty
```

Token estimates use UTF-8 bytes / 4 and are not tokenizer or billing guarantees. Expected-path recall is not equivalent to final-answer correctness.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Safety and correctness

The scanner skips secret-like paths, symlinks, generated/binary/oversized files by default. Static dependency facts are not runtime call-graph guarantees. Heuristic language parsers are deliberately conservative. Fan-in surfaces disagreement but never decides which side is true.

For full architecture, policies, provider contracts, workflows and v1.5 design notes, see `references/` and `docs/audits/`.

## License

MIT
