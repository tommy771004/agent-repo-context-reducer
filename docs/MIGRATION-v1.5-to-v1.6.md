# Migration: v1.5 -> v1.6

v1.6 is additive for the v1.5 Fan-In contract. Existing `repo-context-fan-in` usage remains supported.

## Preferred CLI

Old compatibility entry point:

```bash
repo-context-fan-in workers.json --max-estimated-tokens 1800 --pretty
```

Preferred v1.6 entry point:

```bash
repo-context fan-in workers.json --budget 1800 --pretty
```

## New stable boundaries

Use `repo-context schema list` to inspect Draft 2020-12 contracts. Host integrations should validate Worker Output/Handoff/Fan-In/Synthesis Packet payloads at process or transport boundaries.

## Trust semantics

Repository/provider/worker content now carries trust metadata. `instruction_authority: false` is an additive policy field; do not treat `severity: none` as a trust grant.

## Benchmark

Use `repo-context benchmark-e2e examples/benchmark-e2e.json` for deterministic reducer invariants. Existing repository selection benchmarks are unchanged.

## Compatibility

- `repo-context-fan-in` remains installed.
- Existing v1.5 `key/reasons/claims` contradiction fields are retained.
- `canonicalKey` semantics are unchanged.
- Fuzzy semantic merging remains disabled.
