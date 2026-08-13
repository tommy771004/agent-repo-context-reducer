# Agent Handoff Reduction

Do not pass a subagent's raw conversation, search log, or entire tool history to the next agent.

Use a structured handoff containing only the fields that can change the next agent's work:

- summary
- decisions
- evidence
- targets
- constraints
- open questions
- changed files
- tests
- risks

The bundled handoff reducer performs deterministic key selection and bounded truncation. It is lossy by design and records the source hash and optional artifact id for rehydration.
