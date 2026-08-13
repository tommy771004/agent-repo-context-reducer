from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FacadeCommand:
    name: str
    description: str
    mode: str = "context"
    intent: str | None = None
    default_task: str = ""
    default_budget: int = 6000


FACADES: dict[str, FacadeCommand] = {
    "reducer-repo": FacadeCommand(
        name="reducer-repo",
        description="General repository task. Auto-route the request, reuse compatible providers first, then return minimal context.",
        intent=None,
        default_task="Understand this repository and answer the user's repository task.",
    ),
    "reducer-debug": FacadeCommand(
        name="reducer-debug",
        description="Debug a repository issue with provider reuse, graph-guided search, symbol-first reading, and a bounded context pack.",
        intent="debug",
        default_task="Debug the current repository issue.",
    ),
    "reducer-impact": FacadeCommand(
        name="reducer-impact",
        description="Analyze change impact using Git changes, dependency neighborhoods, provider reuse, and bounded context.",
        intent="change-impact",
        default_task="Analyze the impact of the current repository changes.",
    ),
    "reducer-review": FacadeCommand(
        name="reducer-review",
        description="Review code or changes with provider reuse, diff-aware context selection, and bounded source expansion.",
        intent="review",
        default_task="Review the current repository changes.",
    ),
    "reducer-doctor": FacadeCommand(
        name="reducer-doctor",
        description="Detect overlapping Skills/plugins/providers and show which capabilities will be reused versus native fallback.",
        mode="doctor",
        default_task="Check provider and Skill capability overlap.",
        default_budget=0,
    ),
}


def list_facades() -> list[dict[str, Any]]:
    return [
        {
            "name": item.name,
            "description": item.description,
            "mode": item.mode,
            "intent": item.intent,
            "default_budget": item.default_budget,
        }
        for item in FACADES.values()
    ]


def get_facade(name: str) -> FacadeCommand:
    try:
        return FACADES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown reducer command: {name}") from exc
