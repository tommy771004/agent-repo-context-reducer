# Policy: Session Deduplication

Use a stable `--session` identifier throughout one coding/reasoning session.

The gateway fingerprints returned symbol bodies. If unchanged content was already returned in the session, it is omitted. If a previously returned symbol changed, the gateway prefers a unified delta when smaller than the full symbol.

Do not change session IDs simply to force unchanged context to be emitted again.
