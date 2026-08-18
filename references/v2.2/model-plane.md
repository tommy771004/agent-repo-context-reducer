# Thin Model Plane

v2.2 separates rich local reducer state from model-visible evidence. Provenance, trust signals, candidate metadata, full audits, budget internals and telemetry remain in sidecars. Worker requests receive `repo-context-model-context/v1`; grader/integrator requests receive `repo-context-model-packet/v1`.

The grader may receive a source-targeted verification projection containing only repository blocks referenced by synthesis source IDs. The integrator is synthesis-only. This prevents the same repository evidence from being serialized once as lane context and again through synthesis.

Adaptive lane budgets preserve the aggregate repository-context ceiling. Repository tokens no longer needed by synthesis-only integrators are reassigned to evidence workers; graders retain a small verification allocation.
