# Architecture: Task Routing

`repo-context route` is a deterministic keyword/rule classifier. It returns one workflow and only the policies needed by that workflow.

Current task classes:
- understand,
- debug,
- change-impact,
- review.

Routing is explicitly labeled heuristic. The purpose is to reduce documentation/context loading, not to claim semantic task understanding.
