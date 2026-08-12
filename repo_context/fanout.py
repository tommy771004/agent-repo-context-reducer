from __future__ import annotations

from typing import Any


def recommend_fanout(coverage: float | None, unresolved_count: int, used_subagents: int,
                     max_subagents: int = 4, concurrency: int = 2) -> dict[str, Any]:
    cov = 0.0 if coverage is None else max(0.0, min(1.0, coverage))
    remaining = max(0, max_subagents - used_subagents)
    if cov >= 0.85 or unresolved_count <= 0 or remaining <= 0:
        launch = 0
    else:
        launch = min(concurrency, remaining, max(1, unresolved_count))
    return {
        "recommended_new_subagents": launch,
        "max_subagents": max_subagents,
        "concurrency": concurrency,
        "recommend_cancel_remaining": bool(cov >= 0.9 and used_subagents > 0),
        "classification": "heuristic-backpressure-policy",
        "reason": "stop/high-coverage" if launch == 0 else "expand-only-for-unresolved-evidence",
        "note": "Actual cancellation requires integration with the agent runtime.",
    }
