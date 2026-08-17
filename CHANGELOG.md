# Changelog

## 1.5.0

- Added deterministic multi-worker Fan-In Reducer for the parallel-worker → final-agent boundary.
- Added exact/canonical grouping, agreement metadata, malformed diagnostics, and structured value/polarity contradiction surfacing.
- Corrected agreement semantics so contradictory asserted sides under the same fact identity are counted separately (for example async 2 vs sync 1, never agreement 3).
- Added bounded Synthesis Packet generation that preserves contradictions even when mandatory evidence exceeds the target budget.
- Upgraded `reduce_handoff()` with optional token-aware field selection while preserving backward-compatible char/item bounds.
- Added deterministic fan-in benchmark metrics for raw worker tokens, reduced tokens, synthesis packet tokens, reducer latency, duplicate/agreement/contradiction counts, and explicit unmeasured host metrics.
- Added reducer-stage trace events and replay summaries.
- Added `repo-context-fan-in` CLI entry point and example input.
- Added native `context.fan-in`, `context.contradiction`, and `context.synthesis-packet` capabilities.
- Kept fuzzy semantic merge disabled by default to preserve the project's correctness-first policy.

## 1.4.0

- Made project-scope host shortcuts portable and added renderer drift tests.
- Consolidated persistent runtime state under `.repo-context/`.
- Expanded structural extraction for C/C++, shell, PowerShell and SQL.
- Added symbol reads for the new language tiers.
- Added host uninstall, update/remove maintenance surfaces, cache generation guards, manifest consistency tests and distinct map/query contracts.
- Reworked documentation around Core Reducer vs optional Advisory Harness Planner.

## 1.3.0

- Added deterministic risk/ambiguity routing and vendor-neutral model tiers.
- Added per-lane budgets, independent quality gate and bounded retry/tier escalation.

## 1.2.0

- Added task complexity routing, dependency-aware scheduling, handoff reducer and artifact store.
- Added knowledge/executor/orchestration/context capability layers and local docs/ADR lexical fallback.

## 1.1.0

- Added reducer intent facades and Claude Code/Codex host adapters.

## 0.2.0

- Added progressive Top-K output, task-aware ranking, dependency graph, changed/module/deps modes, cache and safety guards.

## 0.1.0

- Initial repository structural scanner and Agent Skill.
