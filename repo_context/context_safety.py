from __future__ import annotations

from typing import Any


def assess_context_sufficiency(context_pack: dict[str, Any] | None) -> dict[str, Any]:
    """Deterministic pre-model check for whether another local recall pass is warranted.

    This is intentionally conservative and does not claim semantic completeness. It only
    turns explicit local signals (no evidence, low lexical coverage, stale invalidation)
    into a host action: continue or recall. It never calls a model.
    """
    if not isinstance(context_pack, dict):
        return {
            "classification": "deterministic-context-sufficiency-gate",
            "sufficient": False, "recommended_action": "recall", "reasons": ["missing-context-pack"],
            "model_calls_added": 0,
        }
    files = [x for x in context_pack.get("files") or [] if isinstance(x, dict)]
    symbols = [x for x in context_pack.get("symbols") or [] if isinstance(x, dict)]
    external = [x for x in context_pack.get("external_context") or [] if isinstance(x, dict)]
    evidence_count = len(files) + len(symbols) + len(external)
    coverage = context_pack.get("coverage") if isinstance(context_pack.get("coverage"), dict) else {}
    coverage_score = coverage.get("score")
    reasons: list[str] = []
    if evidence_count == 0:
        reasons.append("no-evidence-selected")
    if isinstance(coverage_score, (int, float)) and float(coverage_score) < 0.34:
        reasons.append("low-lexical-coverage")
    problem_context = context_pack.get("problem_context") if isinstance(context_pack.get("problem_context"), dict) else {}
    problem_requirements = [item for item in problem_context.get("requirements") or [] if isinstance(item, dict)]
    incomplete_problem_ids = [
        str(item.get("id"))
        for item in problem_requirements
        if item.get("status") != "covered"
    ]
    if incomplete_problem_ids:
        reasons.append("problem-evidence-incomplete")
    workflow = problem_context.get("workflow") if isinstance(problem_context.get("workflow"), dict) else {}
    workflow_dimensions = [item for item in workflow.get("dimensions") or [] if isinstance(item, dict)]
    incomplete_workflow_dimension_ids = [
        str(item.get("id"))
        for item in workflow_dimensions
        if item.get("status") != "covered"
    ]
    if incomplete_workflow_dimension_ids:
        reasons.append("workflow-dimension-evidence-incomplete")
    stale = ((context_pack.get("context_store") or {}).get("stale_invalidation_before_refresh") if isinstance(context_pack.get("context_store"), dict) else None)
    if isinstance(stale, dict) and int(stale.get("missing_items") or 0) > 0:
        reasons.append("previous-hot-evidence-missing")
    # Stale evidence alone does not require another recall if the newly built context
    # already selected current evidence and has adequate lexical coverage.
    sufficient = not reasons
    return {
        "classification": "deterministic-context-sufficiency-gate",
        "sufficient": sufficient,
        "recommended_action": "continue" if sufficient else "recall",
        "reasons": reasons,
        "evidence_count": evidence_count,
        "lexical_coverage": coverage_score,
        "problem_count": len(problem_requirements),
        "incomplete_problem_ids": incomplete_problem_ids,
        "workflow_dimension_count": len(workflow_dimensions),
        "incomplete_workflow_dimension_ids": incomplete_workflow_dimension_ids,
        "model_calls_added": 0,
        "note": "Every explicit problem must have evidence before continue is recommended; this is still not a semantic completeness proof.",
    }
