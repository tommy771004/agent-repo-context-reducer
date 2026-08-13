from __future__ import annotations

import pathlib
from typing import Any

from .capabilities import resolve_capability
from .complexity import classify_complexity
from .risk import classify_risk

TIERS = ("cheap", "standard", "strong")
_TIER_RANK = {name: i for i, name in enumerate(TIERS)}


def stronger(tier: str) -> str:
    idx = min(len(TIERS) - 1, _TIER_RANK.get(tier, 1) + 1)
    return TIERS[idx]


def _at_least(tier: str, minimum: str) -> str:
    return tier if _TIER_RANK.get(tier, 1) >= _TIER_RANK[minimum] else minimum


def route_models(task: str, task_type: str | None = None, repo: pathlib.Path | str | None = None) -> dict[str, Any]:
    """Return abstract model tiers. It never assumes a vendor/model name or performs a model call."""
    complexity = classify_complexity(task, task_type)
    risk = classify_risk(task, task_type)
    level = complexity["level"]
    risk_level = risk["level"]

    if level == "trivial":
        roles = {"worker": "cheap", "grader": "cheap"}
    elif level == "focused":
        roles = {"worker": "standard", "grader": "standard"}
    elif level == "complex":
        roles = {"planner": "standard", "researcher": "cheap", "worker": "standard", "grader": "standard"}
    else:
        roles = {"planner": "strong", "researcher": "standard", "worker": "standard", "grader": "strong", "integrator": "strong"}

    reasons: list[str] = [f"complexity:{level}", f"risk:{risk_level}"]
    if risk_level in {"high", "critical"}:
        roles["worker"] = _at_least(roles.get("worker", "standard"), "standard")
        roles["grader"] = "strong"
        if "planner" in roles:
            roles["planner"] = "strong"
        reasons.append("high-cost-of-error")
    if risk["ambiguity"]["score"] >= 0.44 or risk["routing_confidence"] < 0.7:
        if "planner" in roles:
            roles["planner"] = "strong"
        else:
            roles["worker"] = _at_least(roles.get("worker", "cheap"), "standard")
        roles["grader"] = _at_least(roles.get("grader", "cheap"), "standard")
        reasons.append("ambiguity-escalation")
    if risk["novelty"]["score"] > 0:
        if "planner" in roles:
            roles["planner"] = "strong"
        roles["grader"] = _at_least(roles.get("grader", "standard"), "strong")
        reasons.append("novelty-escalation")

    # A cheap sorter may classify/rank, but it may not make high-risk/ambiguous final decisions.
    sorter_policy = {
        "primary": "deterministic",
        "model_calls": 0,
        "fallback_tier": "cheap",
        "fallback_only_when": "deterministic routing is insufficient and the host supports model-tier routing",
        "must_escalate_beyond_cheap_when": ["high-risk", "critical-risk", "ambiguous", "novel-design", "low-routing-confidence"],
    }

    providers: dict[str, Any] = {}
    if repo is not None:
        root = pathlib.Path(repo).resolve()
        for tier in sorted(set(roles.values()), key=lambda x: _TIER_RANK[x]):
            providers[tier] = resolve_capability(root, f"model.{tier}")

    return {
        "classification": "abstract-model-tier-policy",
        "vendor_neutral": True,
        "complexity": complexity,
        "risk": risk,
        "roles": roles,
        "sorter_policy": sorter_policy,
        "reasons": reasons,
        "provider_resolution": providers,
        "execution_note": "Tiers are advisory unless the host/runtime exposes compatible model.* providers; no vendor model is assumed.",
    }
