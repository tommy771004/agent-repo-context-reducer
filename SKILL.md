---
name: agent-repo-context-reducer
description: Provider-aware deterministic repository context reduction for coding agents, including indexing, dependency/symbol navigation, progressive context budgets, reduced handoffs, and safe multi-worker fan-in before final synthesis.
---

# Agent Repo Context Reducer

Use deterministic preprocessing to reduce repository and multi-agent context before reasoning.

## Use this skill when

- a coding task would otherwise require reading a large part of a repository;
- the agent needs architecture, debug, change-impact, or review context;
- multiple workers produce overlapping structured findings;
- a final agent/grader would otherwise receive raw worker conversations;
- context/token budget, provenance, contradiction surfacing, or session dedup matters.

## Default workflow

1. Route the user intent (`understand`, `debug`, `change-impact`, `review`).
2. Reuse a compatible trusted provider when available; otherwise use native fallbacks only for capabilities actually implemented.
3. Build or reuse the repository index/graph.
4. Rank files and symbols for the current task.
5. Emit bounded context; prefer structure/symbol reads over whole-file reads.
6. Track repeated reads with session ledger/delta context.
7. For multi-agent work, reduce each handoff.
8. Fan multiple worker outputs into one deterministic reduction.
9. Preserve malformed diagnostics, agreement metadata and structured contradictions.
10. Build a bounded synthesis packet for the final model/grader.

## Common commands

```bash
repo-context map . --top-k 25 --pretty
repo-context query . "<task>" --top-k 20 --pretty
repo-context context . "<task>" --budget 6000 --session default --pretty
repo-context symbol . path/to/file.py SymbolName --session default --pretty
repo-context plan "<task>" --repo . --pretty
repo-context-fan-in worker-outputs.json --max-estimated-tokens 1800 --pretty
```

## Repository correctness rules

- Do not treat a static import graph as a runtime call graph.
- Do not preload every file or every reference document.
- Prefer explicit task relevance, graph evidence, and symbols before full source.
- Skip secret-like paths, generated/binary/oversized files and symlinks unless a higher-level policy explicitly handles them safely.
- Provider overlap inferred only from description is informational and must not trigger execution.

## Multi-worker fan-in

When two or more worker handoffs converge on one final agent or grader:

1. reduce each worker payload with `reduce_handoff()`;
2. validate fan-in findings;
3. group only by deterministic identity (`canonicalKey` or exact conservative normalized claim);
4. if structured value/polarity exists, keep contradictory asserted sides separate;
5. record agreement only among workers supporting the same asserted side;
6. surface contradictions explicitly;
7. build the synthesis packet within token budget;
8. if mandatory contradictions exceed the budget, keep them and report overflow.

Do **not** fuzzy-merge claims at fan-in. Semantic similarity may propose candidates upstream, but it is not merge proof.

## Handoff fields

Prefer compact structured fields such as `summary`, `decisions`, `evidence`, `targets`, `constraints`, `tests`, `risks`, `open_questions` and `changed_files`. Keep large logs/tool output in artifacts instead of the next model context.

## Harness planner

Complexity/risk/model-tier/schedule/quality/retry output is advisory. The reducer does not spawn agents, switch vendor models, or invoke unsupported executor capabilities by itself.

## Measurement

Token estimates are UTF-8 bytes / 4 approximations. Reduction ratio is useful for comparison but is not an API billing guarantee. Expected-path recall is not final-answer correctness.
