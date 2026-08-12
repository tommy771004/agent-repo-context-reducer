# Workflow: Review

Use for code review, security review, performance review, or maintainability audits.

1. Reuse compatible Git diff, graph, symbol, or review providers where safe and machine-adaptable.
2. For active work, start from changed code rather than the whole repository.
3. Build a bounded context pack using the exact review goal.
4. Inspect high-risk/relevant symbols and only the dependency neighborhood needed to validate a finding.
5. Request whole files only when file-local/cross-symbol invariants require them.
6. Keep findings tied to inspected code and provenance.
7. Do not infer unobserved runtime behavior from a static graph.

Read `../policies/read-admission.md` and `../policies/context-budget.md`.
