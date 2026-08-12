# Trace and Replay

A context run records observational events under `.repo-context/runs/<run-id>.jsonl`.

Trace should answer:

- what task route was selected
- what providers were considered/selected
- how many context blocks were emitted
- approximate tokens used
- coverage/stop recommendation

Replay is observational by default. It must not re-execute shell commands, model calls, writes, deployments or other side effects.
