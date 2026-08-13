# Dependency-Aware Scheduling

Parallelism is allowed only when stages are dependency-independent.

Example:

`plan → research → implement → {test, review} → finalize`

Testing and review may run in parallel after implementation. Implementation must not race ahead of required planning/research. Every cross-agent transition should use a reduced structured handoff instead of the previous agent's full context.

Schedules are advisory. The reducer does not spawn agents itself.
