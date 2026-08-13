---
name: reducer-repo
description: General repository task. Auto-route the request, reuse compatible providers first, then return minimal context.
---

# reducer-repo

Treat the user's request associated with this skill invocation as `<user task>`.
Do not preload the repository. Run the reducer facade first:

```bash
python scripts/repo_context.py run reducer-repo "<user task>" --repo . --pretty
```

Then reason from the returned minimal context. Reuse compatible trusted providers first and let the reducer use native fallback only for missing capabilities. Read full source only when the bounded context is insufficient.
