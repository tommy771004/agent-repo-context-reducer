---
name: agent-repo-context-reducer
description: Prevent AI coding agents from blindly loading repository files or duplicating existing graph/search/agent capabilities. Reuse compatible providers first, then use native fallbacks only where implemented, and keep repository and agent-to-agent context bounded.
---

# Agent Repo Context Reducer

Use this Skill for non-trivial repository understanding, debugging, review, change-impact work, and context-efficient multi-agent engineering workflows.

The **Core Reducer** is the default product surface. Complexity/model-tier/scheduler/grader features are an **optional advisory Harness Planner**; they do not spawn agents or switch models by themselves.

## Human-facing shortcuts

Prefer these intent facades when the host exposes them:

- `reducer-repo` — general repository task; auto-route the request.
- `reducer-debug` — force the debug workflow.
- `reducer-impact` — force the change-impact workflow.
- `reducer-review` — force the review workflow.
- `reducer-doctor` — detect overlapping Skills/plugins/providers and native fallbacks.

Claude Code adapters expose `/reducer-*` commands. Codex adapters install the same names as Skills; use an `@reducer-*` mention only when the current Codex client exposes installed Skills through `@`.

## Default entry rule

Do **not** manually run `status → index → route → context` during normal use.

If a short facade was invoked, run exactly that facade through the shared runtime:

```bash
repo-context run reducer-debug "<user task>" --repo . --pretty
```

If this root Skill was invoked without a specific facade, use:

```bash
repo-context run reducer-repo "<user task>" --repo . --pretty
```

When `repo-context` is not on PATH, run the bundled `scripts/repo_context.py` relative to this Skill directory for direct Skill execution. Project-scope generated host shortcuts intentionally require portable `repo-context` on PATH; only global-scope installation may resolve a machine-local absolute runtime.

All facades share the same provider registry, persistent index, graph, session ledger, artifact store, task budget and trace. Never create a second index because a different shortcut was used.

## Core policy

**Detect before building. Reuse before implementing. Reduce before reasoning. Handoff summaries before histories.**

The runtime should:

1. Classify task intent, complexity, risk, ambiguity and novelty with deterministic code first; do not spend a model call on routing when code is sufficient.
2. Keep trivial/focused work single-agent unless the user explicitly requests otherwise.
3. When model reasoning is needed, choose an abstract `cheap` / `standard` / `strong` tier; never invent a vendor/model mapping that the host does not expose.
4. Resolve only capabilities required by the current task.
5. Reuse compatible trusted providers when available.
6. Treat unknown overlapping Skills as overlap signals, not executable providers.
7. Use native fallback only for capabilities the reducer actually implements.
8. Keep unsupported model/executor/knowledge-graph capabilities unresolved rather than pretending native support.
9. Canonicalize and deduplicate external/native context before it enters model context.
10. Prefer symbol-level evidence over whole-file reads.
11. Store large agent/tool results as artifacts and pass reduced structured handoffs between agents.
12. Parallelize only dependency-independent agent stages and enforce per-lane child budgets inside the task-wide budget.
13. Grade worker output through an independent reduced-evidence quality gate before treating multi-stage work as complete.
14. Bound reject/retry loops; escalate tier when policy requires it and return to human review when the attempt budget is exhausted.
15. Stop expanding when additional context has low expected information value or the task budget is exhausted.

## Progressive reference routing

Do not preload every reference file. Read only the references needed by the current task:

- Multi-agent decision: `references/harness/task-complexity.md`
- Model tier / risk escalation: `references/harness/model-routing.md`
- Independent grader / bounded retry: `references/harness/quality-gate.md`
- Cross-agent transfer: `references/harness/handoff.md`
- Large intermediate outputs: `references/harness/artifacts.md`
- Multi-agent execution order: `references/harness/scheduling.md`
- External knowledge/executor providers: `references/providers/knowledge-executor-layers.md`
- Repository workflows: read only the matching file under `references/workflows/`

## Capability layer boundary

Keep these responsibilities separate:

- `repository.*` — code index, symbols, static dependency graph and repository search.
- `knowledge.*` — docs/history retrieval and optional external knowledge graphs.
- `executor.*` — external coding/autonomous engineering executors.
- `orchestration.*` — scheduling, handoff and optional external multi-agent frameworks.
- `model.*` — optional external mappings for abstract cheap/standard/strong execution tiers.
- `quality.*` — reduced-evidence grading and optional external grader providers.
- `context.*` — budget, per-lane child budgets, deduplication, session state, artifacts and handoff reduction.

The bundled `knowledge.search` fallback is lexical retrieval over local documentation-like files. It is **not** GraphRAG. The native repository graph is a resolved static-import/symbol graph, not a semantic knowledge graph or guaranteed runtime call graph.


## Model routing and quality gate

Use deterministic routing first. `cheap`, `standard`, and `strong` are abstract tiers only. If the host/runtime does not expose a compatible `model.*` provider, keep the mapping advisory/unresolved instead of naming a model.

For multi-stage work, the worker does not self-grade. Build a reduced grader packet from the worker handoff/tests/evidence/risks, apply the risk-aware quality threshold, and use the bounded retry policy. Never loop until pass without an attempt limit.

## Agent handoffs

Never pass a subagent's raw conversation, grep history, failed attempts, or full tool output into another agent by default. Use the deterministic handoff reducer or an equivalent structured contract containing only decisions, evidence, targets, constraints, open questions, changed files, tests and risks. Keep the raw output in the artifact store when later rehydration may be useful.

## Full-file reads

A full source read is an escalation, not the default. If more detail is needed after the facade result, use returned symbol/dependency actions or the read-admission policy before loading a large file.

## Token semantics

Budgets use an approximate UTF-8-bytes/4 estimate unless a provider-specific tokenizer is configured. They are context-selection limits, not billing guarantees.

## Local state semantics

Native index-backed commands can write local state under `.repo-context/` even when the repository analysis itself is read-only. The first state write best-effort adds `.repo-context/` to `.gitignore`. `sync` is cache-aware for source parsing but rebuilds file enumeration, graph/ranking and the persistent JSON index. `--no-sync` means use an existing index only; it must not silently create one.

## Safety

Secret-like files, private keys, symlinks, large binaries, generated/minified output, VCS metadata, dependencies and build directories are excluded by default. External machine adapters are never executed merely because a Skill name looks relevant; they require a compatible manifest/adapter and configured trust policy.
