from __future__ import annotations

from typing import Any

from .complexity import classify_complexity
from .risk import classify_risk


def _waves(nodes: list[dict[str, Any]]) -> list[list[str]]:
    remaining = {n["id"]: set(n.get("depends_on", [])) for n in nodes}
    done: set[str] = set()
    waves: list[list[str]] = []
    while remaining:
        ready = sorted([node for node, deps in remaining.items() if deps <= done])
        if not ready:
            raise ValueError("Scheduler dependency cycle detected")
        waves.append(ready)
        for node in ready:
            remaining.pop(node, None)
            done.add(node)
    return waves


def build_schedule(task: str, task_type: str | None = None,
                   complexity_result: dict[str, Any] | None = None,
                   risk_result: dict[str, Any] | None = None) -> dict[str, Any]:
    complexity = complexity_result or classify_complexity(task, task_type=task_type)
    risk = risk_result or classify_risk(task, task_type=task_type)
    level = complexity["level"]
    need_security = risk["level"] == "critical" or "security" in set(risk.get("signals", []))

    if level in {"trivial", "focused"}:
        nodes = [
            {"id": "work", "role": "worker", "depends_on": []},
            {"id": "grade", "role": "grader", "depends_on": ["work"]},
        ]
    elif level == "complex":
        nodes = [
            {"id": "plan", "role": "planner", "depends_on": []},
            {"id": "research", "role": "researcher", "depends_on": ["plan"]},
            {"id": "implement", "role": "implementer", "depends_on": ["plan", "research"]},
            {"id": "test", "role": "tester", "depends_on": ["implement"]},
        ]
        grade_deps = ["test"]
        if need_security:
            nodes.append({"id": "security", "role": "security-reviewer", "depends_on": ["implement"]})
            grade_deps.append("security")
        nodes.append({"id": "grade", "role": "grader", "depends_on": grade_deps})
    else:
        nodes = [
            {"id": "plan", "role": "planner", "depends_on": []},
            {"id": "research-a", "role": "researcher", "depends_on": ["plan"]},
            {"id": "research-b", "role": "researcher", "depends_on": ["plan"]},
            {"id": "implement", "role": "implementer", "depends_on": ["plan", "research-a", "research-b"]},
            {"id": "test", "role": "tester", "depends_on": ["implement"]},
        ]
        grade_deps = ["test"]
        if need_security:
            nodes.append({"id": "security", "role": "security-reviewer", "depends_on": ["implement"]})
            grade_deps.append("security")
        nodes += [
            {"id": "grade", "role": "grader", "depends_on": grade_deps},
            {"id": "finalize", "role": "integrator", "depends_on": ["grade"]},
        ]

    waves = _waves(nodes)
    return {
        "classification": "heuristic-dependency-aware-schedule",
        "task_type": task_type,
        "complexity": complexity,
        "risk": risk,
        "nodes": nodes,
        "waves": waves,
        "max_parallel_width": max((len(w) for w in waves), default=1),
        "quality_gate_node": "grade",
        "policy": "Only independent nodes may run in parallel. The grader is a separate quality gate and receives reduced handoff evidence, not raw worker conversation.",
    }
