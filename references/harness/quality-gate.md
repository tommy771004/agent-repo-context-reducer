# Independent Quality Gate

A worker result is not trusted merely because it completed. The reducer creates a reduced grader packet and expects an independent quality decision before a result is treated as complete in multi-stage workflows.

## Reduced evidence only

The grader should receive:

- task and constraints,
- reduced worker handoff,
- changed files / diff summary when available,
- tests or verification evidence,
- relevant risks,
- artifact references when raw output must stay outside context.

Do not forward the worker's raw conversation, search history, failed attempts, or large logs by default.

## Risk-aware thresholds

The deterministic gate uses higher pass thresholds for higher-risk tasks. Missing evidence produces `uncertain`, not an implicit pass.

The gate validates a grader response; it is not itself a proof of correctness.

## Bounded retry

Reject loops are finite. A rejected or uncertain result may:

1. retry within the configured worker-attempt budget,
2. escalate the worker tier when risk/ambiguity justifies it,
3. stop and require human review after the bounded attempt budget is exhausted.

Never implement an unbounded `while grader != pass` loop.
