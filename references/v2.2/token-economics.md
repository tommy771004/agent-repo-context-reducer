# End-to-End Token Economics

A final-prompt reduction ratio is insufficient. v2.2 tracks aggregate model input/output across every runtime attempt, estimated data-plane and control-plane input, token amplification, and net savings against a direct single-call baseline.

Local schema checks, hashing, exact dedup, filter audit, provenance calculation and telemetry are CPU/control-plane work and cost zero model tokens unless their serialized output is explicitly placed in a runtime request.

Measurement provenance matters. Provider-reported pipeline tokens compared with an estimator-derived baseline are labeled `mixed-measurement`; their savings result is directional-only. USD cost is never inferred from a static price table.
