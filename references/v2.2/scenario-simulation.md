# Scenario Simulation

`repo-context simulate-reduction` evaluates Direct, Light and Full using explicit deterministic token/latency assumptions. The default suite covers small single-file work, medium repetitive work, large high-duplication investigation, conflicting evidence, large low-duplication provenance-heavy work, security-sensitive small work, and an orchestration-overhead regression case.

The simulator is a routing calibration tool, not a provider billing model and not a correctness predictor. A strategy that is numerically cheaper but fails safety/correctness eligibility is not considered selectable.

Release gates require the default suite to exercise all three modes and require Adaptive to remain no worse than always-Full in aggregate while preserving Full for safety-sensitive/conflicting cases.
