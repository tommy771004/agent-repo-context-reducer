# Agent Repo Context Reducer v2.2.0

v2.2 makes filtering and deduplication a correctness boundary rather than a collection of local heuristics.

## What changed

- Canonical fact identity no longer implies an unstructured assertion match by default. `exact-claim` is the safe default; `legacy-merge` is opt-in compatibility.
- Fan-In distinguishes occurrences, unique worker agreement, unique source locations, and independent evidence identities.
- Candidate similarity remains candidate-only. Deterministic pair verification is followed by component-wide identity/assertion compatibility and ambiguity checks.
- Duplicate external content retains all provider/source/provenance support.
- Handoff dedup is intentionally shallow and set-like; nested sequence semantics are preserved.
- Contradictory sides are mandatory and represented once in synthesis, with their support metadata attached.
- Both batch and streaming diagnostics are bounded.
- Filter audit is executable from CLI and enforced by the runtime.

## Compatibility

The only intentional semantic tightening is unstructured `canonicalKey` grouping. Callers that intentionally relied on v1.5–v2.1 canonical-only grouping can use:

```bash
repo-context fan-in workers.json --unstructured-canonical-policy legacy-merge
```

The audit reports ambiguous legacy groups. Structured `value` or `polarity` is preferred.

## Safety boundary

The filter audit proves reducer-internal invariants, not semantic truth. Semantic/embedding providers never receive merge authority. Repository/provider/worker text remains untrusted evidence. Existing v2.1 container-sandbox limitations remain unchanged.
