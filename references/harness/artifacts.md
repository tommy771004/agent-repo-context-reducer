# Artifact store

Large agent/tool payloads belong in `.repo-context/artifacts/`. Downstream agents should receive compact metadata or a reduced handoff, not the entire stored payload by default.
