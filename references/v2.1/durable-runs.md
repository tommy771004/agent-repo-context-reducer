# Durable runs and resume

Each runtime run can persist `.repo-context/runtime-runs/<run-id>/checkpoint.json`.

The checkpoint contains hashes and bounded runtime state, not the raw runtime configuration. Large node payloads may be omitted from checkpoint storage while reduced handoffs and bounded worker finding envelopes remain available for downstream resume.

Resume validates:

1. task identity;
2. adapter identity;
3. runtime-config SHA-256;
4. deterministic plan SHA-256;
5. budget/tokenizer/fail-fast policy SHA-256;
6. Git repository working-state identity when available.

Successful nodes are reused. Failed, cancelled, skipped, or unfinished nodes are eligible to run again. Model-call/token counters and telemetry continue cumulatively rather than resetting on resume.

A checkpoint is durable state, not a distributed lease. Run one controller per `run_id`.
