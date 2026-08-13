---
description: Debug a repository issue with provider reuse, graph-guided search, symbol-first reading, and a bounded context pack.
argument-hint: <task>
---

# reducer-debug

Use Agent Repo Context Reducer before broad repository exploration.

Run:

```bash
python scripts/repo_context.py run reducer-debug "$ARGUMENTS" --repo . --pretty
```

Rules:
- Do not recursively read the repository before this command.
- Reuse compatible trusted providers when available.
- Use native indexing only for missing or failed capabilities.
- Reason from the returned bounded context first.
- Expand to full files only when the returned evidence is insufficient.
