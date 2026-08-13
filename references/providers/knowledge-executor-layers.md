# Knowledge, Executor, and Orchestration Provider Layers

The reducer separates provider capabilities by responsibility:

- `repository.*`: code index, symbols, static dependency graph and repository search.
- `knowledge.*`: documentation, ADR/history retrieval and optional external knowledge graphs.
- `executor.*`: coding or autonomous engineering executors.
- `orchestration.*`: scheduling, parallel-agent frameworks and handoffs.
- `context.*`: budget, deduplication, session state, artifacts and handoff reduction.

External providers are preferred only when they are compatible, machine-invokable and trusted. Unsupported optional capabilities remain unresolved rather than being falsely reported as native.

The local `knowledge.search` fallback is deterministic lexical retrieval over documentation-like files. It is not a GraphRAG implementation and must not be described as one.
