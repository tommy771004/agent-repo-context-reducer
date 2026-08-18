# Agent Repo Context Reducer v2.3.0

## Context Safety & Recall

v2.3 narrows the product core to **Reduce → Verify → Recall**. The repository index is the single WARM/Recallable locator source; the model sees only a bounded HOT working set. Runtime, sandbox, fan-in and multi-agent orchestration remain available as an optional harness rather than core requirements.

### New core behavior

- Repository-scoped `ContextEvidence` records with deterministic revision/content/assertion verification.
- HOT Context Store overlay under `.repo-context/context-stores/`; no full source and no duplicate WARM index are persisted.
- Deterministic repository recall: exact symbol/path, bounded local source search, and dependency-neighbor reranking.
- Symbol hits hydrate only the symbol span. Module-level source hits hydrate only a small ±2-line snippet.
- Graph proximity is rerank-only and cannot create relevance by itself.
- Strong exact/source-text hits prune low-signal candidate tails before anything becomes model-visible.
- HOT evidence is invalidated on repository revision changes. Git blob identity is preferred when available.
- Refreshed-index reconciliation prevents deleted/recreated evidence from being blocked forever by an old missing tombstone.
- Deterministic context-sufficiency signals can request recall without claiming semantic completeness.
- Critical Evidence Recall benchmark reports initial/final recall, false-filter rate, missed evidence, and recall-added model calls.

### Correctness boundary

Recall is a recovery mechanism, not a semantic completeness oracle. A no/low-coverage result surfaces escalation. `ContextEvidence` may return `unknown`; similarity never becomes proof or merge authority.

### Release validation target

The release gate validates all prior v2.2 filter/dedup/thin-plane/runtime invariants plus v2.3 Context Store, recall, stale invalidation and critical-evidence recovery contracts.
