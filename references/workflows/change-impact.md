# Workflow: Change Impact

Use when the user asks what a modification can affect.

1. Prefer an existing compatible impact/graph provider when available.
2. Otherwise sync the native index and use `changed` or `impact`.
3. Inspect changed symbols before entire files.
4. Expand reverse/static dependencies only to the requested depth.
5. Treat returned neighborhoods as candidate impact, not guaranteed runtime impact.
6. Prefer current-session deltas over rereading unchanged symbols.
7. Stop when the relevant impact boundary is established; do not traverse the whole graph by default.

Read `../policies/session-dedup.md` and `../policies/read-admission.md`.
