from __future__ import annotations

import pathlib
from typing import Any

from .capabilities import resolve_capability

ROUTES = {
    "understand": {
        "workflow": "references/workflows/understand-repo.md",
        "policies": ["references/policies/context-budget.md", "references/policies/progressive-reading.md"],
        "terms": ["architecture", "understand", "overview", "structure", "project", "repo", "repository", "架構", "專案", "理解", "結構", "整體"],
        "capabilities": ["repository.index", "repository.graph", "repository.symbols", "context.budget", "context.dedup"],
    },
    "debug": {
        "workflow": "references/workflows/debug.md",
        "policies": ["references/policies/read-admission.md", "references/policies/context-budget.md", "references/policies/session-dedup.md"],
        "terms": ["bug", "debug", "error", "fail", "failure", "exception", "wrong", "issue", "why", "broken", "問題", "錯誤", "失敗", "異常", "為什麼", "除錯"],
        "capabilities": ["repository.search", "repository.graph", "repository.symbols", "code.read-symbol", "context.budget", "context.dedup"],
    },
    "change-impact": {
        "workflow": "references/workflows/change-impact.md",
        "policies": ["references/policies/read-admission.md", "references/policies/session-dedup.md"],
        "terms": ["impact", "affected", "change", "changed", "modify", "modified", "regression", "影響", "修改", "變更", "改動"],
        "capabilities": ["git.changed", "repository.graph", "repository.impact", "context.dedup"],
    },
    "review": {
        "workflow": "references/workflows/review.md",
        "policies": ["references/policies/read-admission.md", "references/policies/context-budget.md"],
        "terms": ["review", "audit", "security", "performance", "quality", "pr", "code review", "審查", "檢查", "資安", "效能"],
        "capabilities": ["git.diff", "repository.symbols", "repository.references", "context.budget", "context.dedup"],
    },
}


def route_task(task: str, repo: pathlib.Path | str | None = None) -> dict[str, Any]:
    text = task.lower()
    scores: dict[str, int] = {}
    for name, rule in ROUTES.items():
        score = 0
        for term in rule["terms"]:
            if term.lower() in text:
                score += 2 if len(term) > 3 else 1
        scores[name] = score
    selected = max(scores, key=lambda k: (scores[k], k)) if any(scores.values()) else "understand"
    rule = ROUTES[selected]
    required = list(rule["capabilities"])
    result: dict[str, Any] = {
        "task_type": selected,
        "classification": "heuristic",
        "scores": scores,
        "workflow": rule["workflow"],
        "policies": rule["policies"],
        "required_capabilities": required,
        "context_strategy": "detect-reuse-delegate-native-fallback",
        "recommended_command": f'repo-context context . {task!r} --budget 6000',
        "routing_rule": "Read only the returned workflow/policy references; do not preload every reference file.",
    }
    if repo is not None:
        resolutions = {cap: resolve_capability(repo, cap) for cap in required}
        result["provider_resolution"] = resolutions
        result["native_fallback_capabilities"] = [cap for cap, r in resolutions.items() if r["selected"].get("source_type") == "native"]
        result["external_capabilities_reused"] = [cap for cap, r in resolutions.items() if r["selected"].get("source_type") != "native"]
        result["potential_skill_overlaps"] = {
            cap: r.get("potential_overlaps", []) for cap, r in resolutions.items() if r.get("potential_overlaps")
        }
    return result
