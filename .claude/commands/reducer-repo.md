---
description: General repository task. Auto-route the request, reuse compatible providers first, then return minimal context.
argument-hint: <task>
---

# reducer-repo

Use Agent Repo Context Reducer before broad repository exploration.

Run:

```bash
repo-context run reducer-repo "$ARGUMENTS" --repo . --pretty
```

Rules:
- Do not recursively read the repository before this command.
- Reuse compatible trusted providers when available.
- Use native indexing only for missing or failed capabilities.
- Reason from the returned bounded context first.
- Expand to full files only when the returned evidence is insufficient.
