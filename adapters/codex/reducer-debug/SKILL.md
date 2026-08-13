---
name: reducer-debug
description: Debug a repository issue with provider reuse, graph-guided search, symbol-first reading, and a bounded context pack.
---

# reducer-debug

Treat the user's request associated with this skill invocation as `<user task>`.
Do not preload the repository. Run the reducer facade first:

```bash
repo-context run reducer-debug "<user task>" --repo . --pretty
```

Then reason from the returned minimal context. Reuse compatible trusted providers first and let the reducer use native fallback only for missing capabilities. Read full source only when the bounded context is insufficient.
