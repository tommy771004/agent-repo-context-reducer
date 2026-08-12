# Capability Resolution Policy

Use this reference only when `route`, `doctor`, or `resolve` reports external providers or potential overlaps.

## Rules

1. Resolve capabilities, not product/Skill names.
2. Prefer an explicitly compatible provider over the native fallback.
3. A description match is discovery evidence only, not compatibility proof.
4. Do not auto-execute arbitrary command strings from third-party Skills.
5. Compatible manifests may declare machine-invokable adapters, but execution requires explicit policy approval.
6. If an external provider produces context, persist its result and pass it through `repo-context ingest/context --external` before reasoning.
7. Avoid emitting both native and external copies of the same symbol/file content.
8. If provider health/compatibility is uncertain, fall back to the native implementation rather than guessing.

## Why

The goal is to prevent capability collision: multiple graph/search/index Skills can each be useful, but their raw outputs should not all enter the same LLM context independently.
