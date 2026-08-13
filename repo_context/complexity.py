from __future__ import annotations

from typing import Any


def classify_complexity(task: str, task_type: str | None = None) -> dict[str, Any]:
    """Heuristically classify task size without invoking an LLM.

    The result is intentionally advisory. It controls how much orchestration is
    allowed, not whether a task is actually difficult for a model.
    """
    text = task.lower().strip()
    score = 0
    signals: list[str] = []

    def hit(points: int, label: str, terms: tuple[str, ...]) -> None:
        nonlocal score
        if any(term in text for term in terms):
            score += points
            signals.append(label)

    if len(text) > 500:
        score += 2; signals.append("long-task-description")
    elif len(text) > 180:
        score += 1; signals.append("medium-task-description")

    hit(1, "multi-file", ("multiple files", "across the repo", "across repository", "many files", "多個檔案", "整個專案"))
    hit(2, "architecture", ("architecture", "architectural", "架構", "系統設計"))
    hit(2, "cross-cutting-change", ("refactor", "migration", "migrate", "upgrade", "rewrite", "重構", "遷移", "升級"))
    hit(2, "integration", ("oauth", "authentication", "authorization", "database", "queue", "payment", "integration", "整合", "驗證", "資料庫"))
    hit(2, "delivery-scope", ("implement feature", "add feature", "end to end", "end-to-end", "ship", "production-ready", "完整實作", "新增功能"))
    hit(3, "autonomous-scope", ("entire project", "whole project", "complete engineering task", "autonomously", "from issue to pr", "整個專案", "全自動"))

    if task_type == "review":
        score = max(score, 2)
    elif task_type == "change-impact":
        score = max(score, 2)

    if score <= 1:
        level, agents = "trivial", 1
    elif score <= 3:
        level, agents = "focused", 1
    elif score <= 6:
        level, agents = "complex", 3
    else:
        level, agents = "autonomous", 4

    roles = {
        "trivial": ["worker"],
        "focused": ["worker"],
        "complex": ["planner", "implementer", "reviewer"],
        "autonomous": ["planner", "researcher", "implementer", "reviewer"],
    }[level]

    return {
        "level": level,
        "score": score,
        "classification": "heuristic",
        "signals": signals,
        "recommended_agents": agents,
        "recommended_roles": roles,
        "multi_agent_recommended": agents > 1,
        "note": "Complexity is a deterministic routing heuristic, not a claim about model difficulty or correctness.",
    }
