# Agent Repo Context Reducer v1.7.0

v1.7 turns the reducer into a more production-scalable context boundary.

Main additions:

- NDJSON streaming fan-in;
- pluggable token estimators;
- Git commit/blob/working-tree provenance;
- candidate detection with deterministic verification and no fuzzy merge authority;
- new CLI commands and Draft 2020-12 contracts;
- expanded regression coverage.

Compatibility: JSON fan-in, native bytes/4 token estimates, existing handoff/context commands and v1.6 schemas remain supported.
