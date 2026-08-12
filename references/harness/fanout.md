# Adaptive Fan-out Policy

Do not start the maximum number of subagents at once.

1. Start with a small bounded wave.
2. Reduce/merge their outputs before the parent agent reads them.
3. Estimate unresolved evidence/coverage.
4. Launch another wave only for unresolved evidence.
5. Recommend cancellation when evidence is sufficient.

Coverage and cancellation thresholds are heuristics. Actual process cancellation requires host-runtime support.
