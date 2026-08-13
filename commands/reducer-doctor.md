---
description: Detect overlapping Skills/plugins/providers and show which capabilities will be reused versus native fallback.
argument-hint: <task>
---

# reducer-doctor

Use Agent Repo Context Reducer before broad repository exploration.

Run:

```bash
python scripts/repo_context.py run reducer-doctor --repo . --pretty
```

Rules:
- Do not recursively read the repository before this command.
- Reuse compatible trusted providers when available.
- Use native indexing only for missing or failed capabilities.
- Reason from the returned bounded context first.
- Expand to full files only when the returned evidence is insufficient.
