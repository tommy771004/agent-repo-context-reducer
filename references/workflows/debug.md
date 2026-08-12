# Workflow: Debug

Use for bugs, failures, exceptions, incorrect behavior, intermittent behavior and root-cause analysis.

1. Reuse any compatible search/graph/symbol provider returned by routing; do not run duplicate providers merely for extra coverage.
2. Route external results through the context gateway before reasoning.
3. Generate a task-specific context pack and inspect the top evidence.
4. Read the smallest relevant symbol body before a whole file.
5. Expand static dependencies only when they answer a concrete unresolved question.
6. Use Git change context when the bug may be a regression.
7. Stop when current evidence is sufficient or task budget is exhausted.
8. Do not treat lexical coverage, VoI, or static import reachability as proof of root cause.

Read `../policies/read-admission.md`, `../policies/context-budget.md`, and `../policies/session-dedup.md`.
