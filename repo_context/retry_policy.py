from __future__ import annotations

from typing import Any

from .model_router import stronger


def retry_policy(risk_level: str, complexity_level: str) -> dict[str, Any]:
    # Keep the loop bounded. Higher-risk work escalates faster instead of retrying indefinitely.
    max_attempts = 2 if risk_level in {"high", "critical"} else (3 if complexity_level in {"complex", "autonomous"} else 2)
    return {
        "max_worker_attempts": max_attempts,
        "same_tier_retries": 0 if risk_level in {"high", "critical"} else 1,
        "on_exhaustion": "human-review",
        "classification": "bounded-retry-policy",
    }


def decide_retry(*, decision: str, attempt: int, worker_tier: str, risk_level: str,
                 complexity_level: str, force_escalation: bool = False) -> dict[str, Any]:
    policy = retry_policy(risk_level, complexity_level)
    attempt = max(1, int(attempt))
    if decision == "pass":
        return {"action": "done", "next_tier": None, "attempt": attempt, "policy": policy}
    if decision not in {"reject", "uncertain"}:
        return {"action": "invalid-grade", "next_tier": None, "attempt": attempt, "policy": policy}
    if attempt >= policy["max_worker_attempts"]:
        return {"action": "human-review", "next_tier": None, "attempt": attempt, "policy": policy,
                "reason": "bounded-attempts-exhausted"}

    escalate = force_escalation or decision == "uncertain" or risk_level in {"high", "critical"} or attempt > policy["same_tier_retries"]
    next_tier = stronger(worker_tier) if escalate else worker_tier
    return {
        "action": "retry",
        "next_tier": next_tier,
        "attempt": attempt,
        "next_attempt": attempt + 1,
        "policy": policy,
        "reason": "escalate-tier" if next_tier != worker_tier else "bounded-same-tier-retry",
    }
