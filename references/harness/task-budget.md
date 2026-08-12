# Task-wide Budget Policy

Context tokens are only one resource. Track at least:

- approximate context tokens
- output token allowance
- tool calls
- model calls
- subagent count
- elapsed wall time

A budget is policy/accounting unless the host runtime exposes enforcement hooks.

When a limit is exhausted, prefer answering with current evidence, surfacing missing evidence, or asking the runtime to stop further exploration rather than silently continuing.
