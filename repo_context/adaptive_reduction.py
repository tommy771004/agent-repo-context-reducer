from __future__ import annotations

from typing import Any

from .complexity import classify_complexity
from .risk import classify_risk
from .token_economics import summarize_token_economics

MODES = ("direct", "light", "full")


def eligible_modes(
    *,
    complexity_level: str,
    risk_level: str,
    conflict_ratio: float = 0.0,
    requires_parallel_evidence: bool = False,
) -> dict[str, dict[str, Any]]:
    conflict = max(0.0, float(conflict_ratio))
    direct_reasons: list[str] = []
    light_reasons: list[str] = []
    if complexity_level in {"complex", "autonomous"}:
        direct_reasons.append("complexity-requires-structured-work")
    if risk_level != "low":
        direct_reasons.append("non-low-risk-requires-quality-gate")
    if conflict >= 0.03:
        direct_reasons.append("material-conflict-rate")
    if requires_parallel_evidence:
        direct_reasons.append("parallel-evidence-required")

    if complexity_level == "autonomous":
        light_reasons.append("autonomous-scope-requires-full-orchestration")
    if risk_level in {"high", "critical"}:
        light_reasons.append("high-risk-requires-full-quality-path")
    if conflict >= 0.08:
        light_reasons.append("high-conflict-rate-requires-full-fan-in")
    if requires_parallel_evidence:
        light_reasons.append("parallel-evidence-required")

    return {
        "direct": {"eligible": not direct_reasons, "blocked_by": direct_reasons},
        "light": {"eligible": not light_reasons, "blocked_by": light_reasons},
        "full": {"eligible": True, "blocked_by": []},
    }


def project_reduction_mode(
    mode: str,
    *,
    source_tokens: int,
    baseline_output_tokens: int = 800,
    duplicate_ratio: float = 0.0,
    conflict_ratio: float = 0.0,
    workers: int = 1,
) -> dict[str, Any]:
    """Project model-visible token economics for an already-local-filtered pipeline.

    All modes receive the same deterministic local filtering benefit. Extra model calls
    are therefore charged as orchestration overhead instead of pretending that Light/Full
    uniquely own exact deduplication. The numbers are routing estimates, not billing.
    """
    if mode not in MODES:
        raise ValueError(f"unknown reduction mode: {mode}")
    source = max(1, int(source_tokens))
    baseline_output = max(0, int(baseline_output_tokens))
    dup = min(1.0, max(0.0, float(duplicate_ratio)))
    conflict = min(1.0, max(0.0, float(conflict_ratio)))
    workers = max(1, int(workers))
    local_savings = min(0.72, dup * 0.85)
    filtered_context = max(256, round(source * (1.0 - local_savings)))

    if mode == "direct":
        input_tokens = filtered_context + 220
        output_tokens = baseline_output
        model_calls = 1
        latency_units = 1.0
    elif mode == "light":
        # One worker + one grader. Grader sees a source-targeted verification projection
        # plus the thin synthesis packet, not another full repository context copy.
        worker_context = round(filtered_context * 0.88)
        verification_context = filtered_context - worker_context
        synthesis = max(160, round(baseline_output * 0.38))
        input_tokens = worker_context + 220 + verification_context + synthesis + 180
        grader_output = max(80, round(baseline_output * 0.12))
        output_tokens = baseline_output + grader_output
        model_calls = 2
        latency_units = 1.55
    else:
        # Aggregate repository context remains bounded and split across evidence lanes.
        # Parallelism repeats task/control framing and produces more worker output, but does
        # not receive a full repository copy per worker. Integrator is synthesis-only.
        evidence_context = round(filtered_context * 0.90)
        worker_control = 200 * workers
        worker_outputs = max(200, round(baseline_output * 0.24 * workers))
        conflict_overhead = round(filtered_context * min(0.10, conflict * 0.30))
        synthesis = max(220, round(worker_outputs * 0.62)) + conflict_overhead
        verification_context = filtered_context - evidence_context
        grader_input = verification_context + synthesis + 180
        integrator_input = synthesis + 180
        input_tokens = evidence_context + worker_control + grader_input + integrator_input
        grader_output = max(100, round(baseline_output * 0.14))
        output_tokens = worker_outputs + grader_output + baseline_output
        model_calls = workers + 2
        latency_units = 2.0 + 0.22 * workers

    economics = summarize_token_economics(
        aggregate_input_tokens=input_tokens,
        aggregate_output_tokens=output_tokens,
        baseline_input_tokens=filtered_context + 220,
        baseline_output_tokens=baseline_output,
        baseline_classification="simulated-filtered-direct-single-call-baseline",
    )
    return {
        "mode": mode,
        "filtered_context_tokens": filtered_context,
        "aggregate_model_input_tokens": input_tokens,
        "aggregate_model_output_tokens": output_tokens,
        "total_model_tokens": input_tokens + output_tokens,
        "model_calls": model_calls,
        "latency_proxy_units": round(latency_units, 2),
        "token_economics": economics,
    }


def choose_reduction_mode(
    task: str,
    *,
    source_tokens: int,
    duplicate_ratio: float = 0.0,
    conflict_ratio: float = 0.0,
    task_type: str | None = None,
    complexity: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
    requires_parallel_evidence: bool = False,
) -> dict[str, Any]:
    complexity = complexity or classify_complexity(task, task_type)
    risk = risk or classify_risk(task, task_type)
    level = str(complexity.get("level") or "focused")
    risk_level = str(risk.get("level") or "low")
    tokens = max(0, int(source_tokens))
    dup = min(1.0, max(0.0, float(duplicate_ratio)))
    conflict = min(1.0, max(0.0, float(conflict_ratio)))
    text = task.lower()
    explicit_parallel_terms = (
        "conflict", "contradiction", "contradictory", "independent evidence", "independent source",
        "cross-check", "cross check", "multiple agents", "衝突", "矛盾", "獨立證據", "多方驗證",
    )
    requires_parallel_evidence = bool(
        requires_parallel_evidence
        or bool(complexity.get("multi_agent_recommended"))
        or any(term in text for term in explicit_parallel_terms)
    )
    eligibility = eligible_modes(
        complexity_level=level,
        risk_level=risk_level,
        conflict_ratio=conflict,
        requires_parallel_evidence=requires_parallel_evidence,
    )

    # Safety constraints run before economics. Deterministic local filtering is shared by
    # every mode, so a more complex model path must justify its *additional* calls rather
    # than receiving artificial credit for local deduplication.
    worker_hint = 2 if requires_parallel_evidence else 3 if level in {"complex", "autonomous"} else 1
    projections = {
        mode: project_reduction_mode(
            mode, source_tokens=tokens, duplicate_ratio=dup, conflict_ratio=conflict,
            workers=worker_hint,
        )
        for mode in MODES
    }
    candidates = [projections[mode] for mode in MODES if eligibility[mode]["eligible"]]
    selected_projection = min(candidates, key=lambda p: (p["total_model_tokens"], p["model_calls"], p["latency_proxy_units"], p["mode"]))
    # Avoid architecture churn for tiny projected differences. Direct remains preferred
    # unless a more complex eligible path saves at least 3% and 256 projected tokens.
    if eligibility["direct"]["eligible"] and selected_projection["mode"] != "direct":
        direct = projections["direct"]
        savings = direct["total_model_tokens"] - selected_projection["total_model_tokens"]
        if savings < 256 or savings / max(1, direct["total_model_tokens"]) < 0.03:
            selected_projection = direct
    selected = selected_projection["mode"]
    reason = "safety-eligible-mode-with-lowest-projected-model-token-overhead"

    return {
        "schema": "repo-context-adaptive-reduction/v1",
        "classification": "deterministic-safety-first-reduction-routing",
        "selected_mode": selected,
        "reason": reason,
        "inputs": {
            "source_tokens": tokens,
            "duplicate_ratio": dup,
            "conflict_ratio": conflict,
            "complexity_level": level,
            "risk_level": risk_level,
            "requires_parallel_evidence": bool(requires_parallel_evidence),
        },
        "eligibility": eligibility,
        "projections": projections,
        "policy": "Safety/correctness constraints first; deterministic local filtering applies to every mode; projected model token economics only ranks already-eligible modes.",
    }


def adapt_schedule(schedule: dict[str, Any], mode: str, *, requires_parallel_evidence: bool = False) -> dict[str, Any]:
    """Return a reduced orchestration schedule for an explicitly selected mode.

    direct: one worker call, only for already-eligible low-risk/simple scenarios.
    light: one worker plus grader.
    full: preserve the original dependency-aware schedule.
    """
    if mode not in MODES:
        raise ValueError(f"unknown reduction mode: {mode}")
    if mode == "full":
        out = dict(schedule)
        out["reduction_mode"] = "full"
        if requires_parallel_evidence and int(out.get("max_parallel_width", 1) or 1) < 2:
            nodes = [
                {"id": "research-a", "role": "researcher", "depends_on": []},
                {"id": "research-b", "role": "researcher", "depends_on": []},
                {"id": "grade", "role": "grader", "depends_on": ["research-a", "research-b"]},
                {"id": "finalize", "role": "integrator", "depends_on": ["grade"]},
            ]
            out.update({
                "classification": "adaptive-parallel-evidence-schedule",
                "nodes": nodes,
                "waves": [["research-a", "research-b"], ["grade"], ["finalize"]],
                "max_parallel_width": 2,
                "quality_gate_node": "grade",
                "parallel_evidence_required": True,
                "policy": "Two independent evidence lanes are mandatory before grading/integration.",
            })
        return out
    task_type = schedule.get("task_type")
    complexity = schedule.get("complexity")
    risk = schedule.get("risk")
    if mode == "direct":
        nodes = [{"id": "work", "role": "worker", "depends_on": []}]
        waves = [["work"]]
        quality_gate = None
    else:
        nodes = [
            {"id": "work", "role": "worker", "depends_on": []},
            {"id": "grade", "role": "grader", "depends_on": ["work"]},
        ]
        waves = [["work"], ["grade"]]
        quality_gate = "grade"
    return {
        "classification": "adaptive-reduction-schedule",
        "task_type": task_type,
        "complexity": complexity,
        "risk": risk,
        "nodes": nodes,
        "waves": waves,
        "max_parallel_width": 1,
        "quality_gate_node": quality_gate,
        "reduction_mode": mode,
        "policy": "Schedule was explicitly reduced after safety/correctness eligibility checks.",
    }
