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
        "model_calls_added": 0,
        "note": "This gate detects explicit context gaps only; it is not a semantic completeness proof.",
    }
