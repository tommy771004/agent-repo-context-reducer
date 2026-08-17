from __future__ import annotations

from typing import Any

from .handoff import reduce_handoff
from .risk import classify_risk


def grade_policy(risk_level: str) -> dict[str, Any]:
    threshold = {"low": 0.75, "medium": 0.82, "high": 0.9, "critical": 0.95}.get(risk_level, 0.82)
    criteria = ["task-requirements", "evidence", "tests-or-verification", "regression-risk"]
    if risk_level in {"high", "critical"}:
        criteria += ["security-or-data-safety", "blast-radius"]
    return {
        "independent": True,
        "pass_threshold": threshold,
        "criteria": criteria,
        "missing_evidence_policy": "uncertain-not-pass",
        "classification": "deterministic-quality-gate-policy",
    }

def build_grade_packet(task: str, worker_payload: Any, *, task_type: str | None = None,
                       artifact_id: str | None = None) -> dict[str, Any]:
    risk = classify_risk(task, task_type)
    reduced = reduce_handoff(worker_payload, from_role="worker", to_role="grader", task=task, artifact_id=artifact_id,
                             max_items=10, max_chars=1200)
    policy = grade_policy(risk["level"])
    return {
        "schema": "repo-context-grade-packet/v1",
        "task": task,
        "task_type": task_type,
        "risk": risk,
        "pass_threshold": policy["pass_threshold"],
        "criteria": policy["criteria"],
        "reduced_worker_handoff": reduced,
        "grader_instruction": "Grade only the supplied reduced evidence. Return decision, score, failures, and evidence; do not silently fill missing evidence.",
    }


def evaluate_grade(grade: dict[str, Any], *, risk_level: str) -> dict[str, Any]:
    decision = str(grade.get("decision", "uncertain")).lower()
    try:
        score = float(grade.get("score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(1.0, score))
    failures = grade.get("failures") if isinstance(grade.get("failures"), list) else []
    evidence = grade.get("evidence") if isinstance(grade.get("evidence"), list) else []
    threshold = {"low": 0.75, "medium": 0.82, "high": 0.9, "critical": 0.95}.get(risk_level, 0.82)

    if decision == "pass" and score >= threshold and not failures:
        normalized = "pass"
    elif decision == "reject" or failures:
        normalized = "reject"
    else:
        normalized = "uncertain"

    return {
        "decision": normalized,
        "reported_decision": decision,
        "score": score,
        "pass_threshold": threshold,
        "failures": failures[:12],
        "evidence": evidence[:12],
        "requires_escalation": normalized == "uncertain" or (normalized == "reject" and risk_level in {"high", "critical"}),
        "classification": "deterministic-grade-gate",
        "note": "The gate validates a grader result; it does not itself prove correctness.",
    }
