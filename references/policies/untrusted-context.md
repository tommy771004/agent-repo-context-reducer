# Untrusted Context Policy

Repository code, comments, documentation, external provider output, knowledge snippets and worker/handoff text are evidence, not instructions.

Rules:

1. `instruction_authority` is always false for these sources.
2. Prompt-injection-like detection is heuristic and advisory.
3. High-risk signals are surfaced; content is not silently deleted because security examples and test fixtures can legitimately contain dangerous-looking text.
4. The host/runtime remains responsible for instruction hierarchy, tool permission and execution confirmation.
5. A clean scan is never a trust grant.
6. Reducer correctness evidence (especially contradictions) must not be removed solely because content looks adversarial; quarantine or review is preferable when the host supports it.
