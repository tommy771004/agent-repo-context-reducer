from __future__ import annotations

import re
from typing import Any


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def evaluate_final_answer(answer: Any, case: dict[str, Any]) -> dict[str, Any]:
    """Deterministic final-answer gate for benchmarkable invariants.

    This deliberately does not claim semantic correctness. It measures explicit required /
    forbidden phrases, structured fields and optional grader decision requirements.
    """
    if isinstance(answer, dict):
        text = str(answer.get("answer") or answer.get("summary") or answer.get("result") or answer)
        structured = answer
    else:
        text = str(answer)
        structured = {}
    hay = _norm(text)
    required = [str(x) for x in case.get("required_claims", [])]
    forbidden = [str(x) for x in case.get("forbidden_claims", [])]
    required_fields = [str(x) for x in case.get("required_fields", [])]
    required_hits = [claim for claim in required if _norm(claim) in hay]
    missing_required = [claim for claim in required if claim not in required_hits]
    forbidden_hits = [claim for claim in forbidden if _norm(claim) in hay]
    missing_fields = [field for field in required_fields if field not in structured]
    expected_decision = case.get("expected_decision")
    decision = structured.get("decision") if isinstance(structured, dict) else None
    decision_ok = expected_decision is None or str(decision).lower() == str(expected_decision).lower()
    passed = not missing_required and not forbidden_hits and not missing_fields and decision_ok
    return {
        "schema": "repo-context-final-answer-evaluation/v1",
        "classification": "deterministic-final-answer-invariant-check",
        "passed": passed,
        "required_claims": required,
        "required_hits": required_hits,
        "missing_required_claims": missing_required,
        "forbidden_claims": forbidden,
        "forbidden_hits": forbidden_hits,
        "required_fields": required_fields,
        "missing_required_fields": missing_fields,
        "expected_decision": expected_decision,
        "reported_decision": decision,
        "decision_ok": decision_ok,
        "note": "Passing this deterministic gate is not proof of semantic or real-world correctness.",
    }
