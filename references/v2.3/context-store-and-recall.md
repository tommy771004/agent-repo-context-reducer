# Context Store and Recall

## State model

```text
Repository source
   ↓
.repo-context/index.json        WARM / Recallable / single locator source
   ↓ rank + filter + budget
Context Store HOT overlay       Active IDs/revisions only
   ↓ projection
Model-visible context           Bounded evidence only
```

The Context Store deliberately does not duplicate the repository index or persist source bodies. It stores only current HOT evidence, bounded rejected tombstones, and bounded invalidation history.

## Recall cascade

1. Exact symbol/path locator.
2. Lexical path/symbol/signature signal.
3. Bounded local source search (`rg` when available, otherwise index-admitted Python fallback).
4. Dependency graph proximity as reranking only.
5. Strong-hit tail pruning.
6. Hard token-budget hydration.

No model call is required by this cascade.

## Rehydration

- Symbol locator → exact source span.
- Module-level text hit → ±2-line source snippet around at most three hits.
- File locator without a text hit → structural file metadata.

Full-file source is not the default recall unit.
