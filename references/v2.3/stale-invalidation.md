# Stale Context Invalidation

HOT repository evidence is revision-bound.

- With Git, content/blob identity is preferred so a timestamp-only `touch` does not create a false stale event.
- Without Git, the index/file stat fingerprint is used as a conservative local identity.
- Changed HOT evidence is removed from the active overlay before reuse.
- Missing HOT evidence becomes a bounded rejected tombstone.
- A refreshed repository index can clear a missing tombstone when the logical locator exists again.
- A HOT locator no longer present in the refreshed index cannot remain active.

This is a context-correctness guard, not a filesystem history database. The repository/Git remains the source of truth.
