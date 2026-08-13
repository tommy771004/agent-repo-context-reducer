# Artifact Store

Large agent and tool outputs should persist outside model context under `.repo-context/artifacts/`.

The model should receive compact artifact metadata or a reduced handoff first. Rehydrate the raw payload only when it has clear expected information value.

Artifacts include a SHA-256 fingerprint, byte size, approximate token size, producer, kind, metadata and payload. `.repo-context/` remains ignored by the repository scanner.
