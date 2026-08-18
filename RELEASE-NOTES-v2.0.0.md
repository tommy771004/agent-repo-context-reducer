# Agent Repo Context Reducer v2.0.0

v2.0 turns the optional harness plan into an explicitly executable runtime boundary while preserving the deterministic reducer core.

New runtime surfaces include actual dependency-wave worker execution, bounded concurrency/retry/cancellation, lane context slicing, pre-grader Fan-In synthesis, executable grader gating, provider-usage telemetry and deterministic final-answer invariants.

The built-in subprocess adapter is intentionally conservative: it is disabled without explicit authorization, uses `shell=False`, communicates through JSON stdin/stdout, minimizes inherited environment data and bounds worker output. It is not a sandbox; untrusted workers should run behind an isolated external runtime adapter.
