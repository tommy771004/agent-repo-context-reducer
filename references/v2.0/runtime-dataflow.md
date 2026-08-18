# v2.0 Runtime Data Flow

```text
repository context planner
  -> ranked bounded context
  -> lane context slicing
  -> dependency wave workers
  -> per-worker reduced handoff
  -> accumulated deterministic fan-in
  -> contradiction-preserving synthesis packet
  -> grader
  -> executable quality gate
  -> integrator/final payload
  -> deterministic final-answer invariants
```

The grader and integrator receive the synthesis packet **before** invocation. Fan-in is not a post-hoc metric.

Context slicing preserves the existing pre-ranked order. It does not introduce semantic similarity as an admission authority. Mandatory dependency handoffs are separate from repository context and remain untrusted evidence.
