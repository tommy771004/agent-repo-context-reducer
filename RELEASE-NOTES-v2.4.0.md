# Agent Repo Context Reducer v2.4.0

## Claim-Aware Verification Recall

v2.4 keeps the project centered on `Reduce → Verify → Recall` and addresses a failure observed in real repository analysis: a small context slice can be locally plausible but globally misleading.

New core command:

```bash
repo-context claim-recall "<provisional claim>" --repo . --path path/to/source --budget 1200 --pretty
```

The reducer deterministically derives verification requirements, performs scoped local source checks, returns compact positive/negative observations, and rehydrates only bounded evidence. The stage adds zero required model calls and never claims semantic truth.

### New safety behavior

- responsive breakpoint counter-context is checked separately from base layout classes;
- imports do not count as runtime invocation;
- localization claims can be challenged by scoped hard-coded visible-copy candidates;
- missing requested paths escalate instead of broadening search silently;
- aggregate model-visible budget includes evidence + verification observations + policy;
- results explicitly abstain with `inconclusive` when deterministic evidence is insufficient.

### Compatibility

v2.3 Context Store, deterministic Recall, stale invalidation, Filter/Dedup, Thin Model Plane, Adaptive Reduction, runtime/sandbox harness, and token-economics behavior remain available.
