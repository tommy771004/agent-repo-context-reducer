from __future__ import annotations

from typing import Any

ROLE_WEIGHTS = {
    "sorter": 0.35,
    "planner": 1.2,
    "researcher": 0.75,
    "worker": 1.7,
    "implementer": 1.7,
    "tester": 0.85,
    "verifier": 0.8,
    "grader": 0.9,
    "reviewer": 0.9,
    "security-reviewer": 1.0,
    "integrator": 0.8,
}


def _allocate(total: int, weights: list[float]) -> list[int]:
    if not weights:
        return []
    total = max(0, int(total))
    weight_sum = sum(max(0.01, w) for w in weights)
    raw = [total * max(0.01, w) / weight_sum for w in weights]
    base = [int(x) for x in raw]
    remainder = total - sum(base)
    order = sorted(range(len(raw)), key=lambda i: (raw[i] - base[i], -i), reverse=True)
    for i in order[:remainder]:
        base[i] += 1
    return base


def allocate_lane_budgets(schedule: dict[str, Any], model_policy: dict[str, Any], *,
                          context_tokens: int = 12000, output_tokens: int = 4000,
                          model_calls: int = 10) -> dict[str, Any]:
    nodes = schedule.get("nodes", [])
    roles = model_policy.get("roles", {})
    weights = [ROLE_WEIGHTS.get(str(n.get("role")), 1.0) for n in nodes]
    ctx = _allocate(context_tokens, weights)
    out = _allocate(output_tokens, weights)

    lanes = []
    for i, node in enumerate(nodes):
        role = str(node.get("role", "worker"))
        policy_role = role
        if role == "implementer":
            policy_role = "worker"
        elif role in {"reviewer", "verifier", "security-reviewer"}:
            policy_role = "grader"
        elif role == "tester":
            policy_role = "worker"
        lane = {
            "id": node.get("id"),
            "role": role,
            "model_tier": roles.get(policy_role, roles.get("worker", "standard")),
            "context_tokens": ctx[i] if i < len(ctx) else 0,
            "output_tokens": out[i] if i < len(out) else 0,
            "model_calls": 1,
            "depends_on": list(node.get("depends_on", [])),
        }
        lanes.append(lane)

    requested_calls = len(lanes)
    return {
        "classification": "deterministic-child-budget-allocation",
        "aggregate": {
            "context_tokens": int(context_tokens),
            "output_tokens": int(output_tokens),
            "model_calls": int(model_calls),
        },
        "allocated": {
            "context_tokens": sum(x["context_tokens"] for x in lanes),
            "output_tokens": sum(x["output_tokens"] for x in lanes),
            "base_model_calls": requested_calls,
        },
        "lanes": lanes,
        "within_model_call_budget": requested_calls <= int(model_calls),
        "note": "Lane budgets are child allocations of the existing task budget; they do not increase the aggregate limit.",
    }


def optimize_model_plane_context_budgets(
    lane_budget: dict[str, Any],
    *,
    mode: str,
    verification_fraction: float | None = None,
) -> dict[str, Any]:
    """Reallocate adaptive-mode repository context around thin synthesis packets.

    Graders need only source-targeted verification context and integrators need no second
    repository copy. Their unused repository-context allocation is returned to evidence
    workers while preserving the original aggregate context-token ceiling.
    """
    if mode not in {"direct", "light", "full"}:
        return dict(lane_budget)
    out = {**lane_budget, "lanes": [dict(x) for x in (lane_budget.get("lanes") or [])]}
    lanes = out["lanes"]
    total = max(0, int((out.get("aggregate") or {}).get("context_tokens", 0)))
    if not lanes:
        return out
    if verification_fraction is None:
        verification_fraction = 0.12 if mode == "light" else 0.10
    verification_fraction = min(0.25, max(0.0, float(verification_fraction)))

    graders = [x for x in lanes if x.get("role") == "grader"]
    integrators = [x for x in lanes if x.get("role") == "integrator"]
    evidence = [x for x in lanes if x.get("role") not in {"grader", "integrator"}]
    if mode == "direct" or not graders:
        target_grader = 0
    else:
        target_grader = round(total * verification_fraction)
    per_grader = _allocate(target_grader, [1.0] * len(graders)) if graders else []
    for i, lane in enumerate(graders):
        lane["context_tokens"] = per_grader[i]
        lane["context_mode"] = "source-targeted-verification"
    for lane in integrators:
        lane["context_tokens"] = 0
        lane["context_mode"] = "synthesis-only"

    remaining = max(0, total - sum(int(x.get("context_tokens", 0)) for x in graders))
    if evidence:
        weights = [ROLE_WEIGHTS.get(str(x.get("role")), 1.0) for x in evidence]
        allocated = _allocate(remaining, weights)
        for i, lane in enumerate(evidence):
            lane["context_tokens"] = allocated[i]
            lane["context_mode"] = "repository-evidence"
    out["allocated"] = {
        **(out.get("allocated") or {}),
        "context_tokens": sum(int(x.get("context_tokens", 0)) for x in lanes),
    }
    out["model_plane_context_policy"] = {
        "classification": "thin-synthesis-aware-context-reallocation",
        "mode": mode,
        "aggregate_context_tokens_preserved": sum(int(x.get("context_tokens", 0)) for x in lanes) <= total,
        "grader_verification_fraction": verification_fraction if graders else 0.0,
        "integrator_repository_context_tokens": 0,
        "policy": "Evidence workers receive repository budget not needed by synthesis-only integrators; graders receive source-targeted verification context only.",
    }
    return out
