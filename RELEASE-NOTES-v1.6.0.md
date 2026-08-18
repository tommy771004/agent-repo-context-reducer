# Agent Repo Context Reducer v1.6.0

v1.6 turns the reducer boundaries into explicit runtime contracts and adds a trust boundary around untrusted repository/provider/worker text.

Highlights:

- 8 Draft 2020-12 JSON Schema contracts bundled with source and wheel.
- Main `repo-context fan-in` and `repo-context synthesis-packet` commands.
- `repo-context schema list|get|validate`.
- `repo-context trust-scan` and trust metadata with no instruction authority.
- Deterministic `benchmark-e2e` fixtures for required/forbidden claims, source preservation and contradiction expectations.
- Multi-agent capability planning includes fan-in, contracts, trust boundary and reducer benchmarking.
- 100 regression tests passing, including all retained v1.5/v1.4 behavior.

Non-goals retained:

- no fuzzy merge authority;
- no claim that static imports are runtime call graphs;
- no claim that bytes/4 equals provider billing tokens;
- no claim that deterministic reducer benchmarks prove final LLM answer correctness;
- no autonomous agent spawning without a runtime adapter.
