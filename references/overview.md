# Architecture overview

The runtime has two surfaces: a Core Reducer for repository context and an optional Advisory Harness Planner. Core work is deterministic-first and has zero required model calls. Repository discovery/index/graph/symbol/ranking select bounded context before reasoning. Multi-agent output is reduced at handoff and fan-in boundaries before a final model/grader receives it.

External capabilities are provider-aware: trusted compatible providers may be reused, native fallbacks are used only where implemented, and unsupported executor/model capabilities remain unresolved.
