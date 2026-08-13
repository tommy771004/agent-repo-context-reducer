# Task Complexity Routing

Complexity routing is deterministic and heuristic. It exists to prevent small repository tasks from automatically expanding into multi-agent workflows.

Levels:

- `trivial`: one worker; no multi-agent recommendation.
- `focused`: one worker with bounded repository context.
- `complex`: planner → researcher → implementer, then test/review where useful.
- `autonomous`: a larger dependency-aware schedule may be proposed, but no external executor is invoked unless a compatible trusted provider exists.

The score is not a model-quality or correctness score. It only controls orchestration allowance.
