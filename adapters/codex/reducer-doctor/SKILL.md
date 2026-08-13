---
name: reducer-doctor
description: Detect overlapping Skills/plugins/providers and show which capabilities will be reused versus native fallback.
---

# reducer-doctor

Treat the user's request associated with this skill invocation as `<user task>`.
Do not preload the repository. Run the reducer facade first:

```bash
repo-context run reducer-doctor --repo . --pretty
```

Then reason from the returned minimal context. Reuse compatible trusted providers first and let the reducer use native fallback only for missing capabilities. Read full source only when the bounded context is insufficient.
