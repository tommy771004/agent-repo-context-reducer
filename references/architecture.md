# Architecture

## Primary pipeline

```text
User task
   |
   v
Task router + complexity router
   |
   v
Required / optional capabilities
   |
   v
Capability resolver
   |
   +--> trusted compatible Skill / registered MCP-plugin adapter
   +--> known safe CLI adapter
   +--> native fallback only where implemented
   `--> unresolved when no truthful provider exists
            |
            v
      repository / knowledge / executor / orchestration layers
            |
            v
Context gateway
   |
   +--> canonical identity
   +--> fingerprint
   +--> session dedup / delta
   +--> context lifecycle metadata
   +--> Value-of-Information prioritization
   +--> token budget
   +--> provenance
   |
   v
Minimal context pack
   |
   +--> single worker for trivial/focused tasks
   `--> dependency-aware schedule for larger tasks
            |
            +--> artifact store for large outputs
            `--> reduced structured handoffs between agents
```

## Harness layers

1. Task routing
2. Task complexity routing
3. Capability discovery/resolution
4. Provider trust/health
5. Native deterministic fallback where implemented
6. Repository/code graph layer
7. Knowledge-memory layer
8. Executor provider layer
9. Read admission
10. Context planning/budget/lifecycle
11. Artifact store and agent handoff reduction
12. Dependency-aware multi-agent scheduling/backpressure
13. Tool-risk policy
14. Trace/replay
15. Benchmark/attribution

## Capability boundaries

- `repository.*` — code index, symbols, static dependency graph, references and search.
- `knowledge.*` — documentation/history retrieval and optional external semantic knowledge graphs.
- `executor.*` — external coding/autonomous engineering executors.
- `orchestration.*` — dependency-aware scheduling, handoffs and optional multi-agent frameworks.
- `context.*` — context budget, deduplication, session state, lifecycle, artifacts and handoff reduction.

A provider in one layer does not automatically substitute for a different layer. In particular, a semantic knowledge graph is not assumed to be a static code-dependency graph.

## Provider rule

Native graph/index/symbol implementations are fallbacks. They exist so the project remains useful in an empty environment; they are not intended to duplicate a compatible trusted provider.

Unknown Skills can be detected as potential overlap from metadata, but are not machine-compatible until an adapter/manifest is available. Unsupported optional capabilities such as `executor.autonomous` remain unresolved when no compatible provider exists.

## Native graph semantics

The bundled repository graph resolves local static imports and reverse imports plus indexed definitions. It is not a guaranteed runtime call graph. Dynamic dispatch, reflection, runtime dependency injection and generated runtime links may be absent.

The bundled `knowledge.search` fallback is deterministic lexical retrieval over documentation-like files. It is not GraphRAG and does not infer semantic communities or entity relationships.

## Context and handoff contract

The full repository index and raw artifacts stay outside model context. The gateway emits only budgeted structural/symbol/external blocks with provenance and fingerprints. Session history can replace unchanged symbol bodies with small references.

When work crosses an agent boundary, pass a reduced structured handoff rather than the previous agent's raw conversation/tool history. Keep large raw outputs in the Artifact Store and rehydrate only when needed.

## Scheduling boundary

Schedules are advisory. Only dependency-independent stages may execute in parallel. The reducer does not silently spawn external agents; execution requires a host/orchestrator provider.

## Enforcement boundary

The Python harness can control what **it** emits. A Skill alone cannot universally intercept every built-in Read/Grep/tool call of every agent. Hard enforcement requires host-runtime hooks/plugins/MCP/tool-gateway integration.
