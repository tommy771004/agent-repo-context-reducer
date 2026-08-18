# Adaptive Reduction

Adaptive routing uses three execution modes:

- Direct: one evidence worker.
- Light: evidence worker followed by a grader.
- Full: one or more evidence lanes, Fan-In, grader and integrator.

Deterministic local filtering/dedup applies to every mode. A mode cannot receive artificial token credit for local dedup and cannot be preferred merely by starving its worker of evidence.

Safety/correctness eligibility comes first. Direct requires low risk and no complex/parallel/conflict requirement. High/critical risk, material conflicts and parallel-evidence requirements exclude Light. Economics ranks only modes that remain eligible.

Runtime defaults to `compat` for upgrade compatibility. `--reduction-mode auto` opts into adaptive scheduling.
