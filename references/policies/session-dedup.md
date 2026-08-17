# Session dedup

Track symbol fingerprints across a session. If unchanged, emit a compact reference. If changed, prefer a delta when smaller than the complete symbol. Session state is local runtime metadata.
