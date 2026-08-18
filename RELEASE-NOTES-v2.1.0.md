# Agent Repo Context Reducer v2.1.0

v2.1 hardens v2.0's executable runtime around two production concerns: isolation and recovery.

## Sandbox boundary

`adapter: container` runs workers through Podman/Docker with conservative defaults: no container network, no implicit image pull, read-only repository, read-only root filesystem, dropped capabilities, no-new-privileges, non-root user, bounded tmpfs, PID/memory/CPU limits and JSON stdin/stdout.

External execution, network, and repository write are independent permissions. The container adapter is not a VM and does not claim kernel-level isolation guarantees.

## Durable runs

Runtime state is checkpointed atomically after completed nodes/waves. `runtime resume` restores successful nodes, reduced handoffs, fan-in worker envelopes and aggregate counters, then executes only unfinished/failed work. Telemetry is cumulative across resume operations.

Resume validates runtime-config, plan and budget/tokenizer fingerprints. Git repositories also receive a bounded working-state identity; source drift blocks resume unless the caller explicitly allows it after review.

## Compatibility

All v1.x/v2.0 deterministic reduction, trust-boundary, streaming, provenance, quality-gate and runtime contracts remain available. Runtime core remains dependency-free; Podman/Docker are optional external executors.
