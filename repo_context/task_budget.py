from __future__ import annotations

import json
import pathlib
import time
from dataclasses import dataclass, asdict
from typing import Any

from .storage import state_dir


@dataclass
class BudgetLimits:
    context_tokens: int = 12000
    output_tokens: int = 4000
    tool_calls: int = 30
    model_calls: int = 10
    subagents: int = 4
    wall_seconds: int = 900


class TaskBudget:
    def __init__(self, root: pathlib.Path, run_id: str, limits: BudgetLimits | None = None):
        self.root = root
        self.run_id = run_id
        self.path = state_dir(root) / "budgets" / f"{run_id}.json"
        self.data: dict[str, Any] = {
            "version": 1,
            "run_id": run_id,
            "started_at": int(time.time()),
            "limits": asdict(limits or BudgetLimits()),
            "used": {"context_tokens": 0, "output_tokens": 0, "tool_calls": 0, "model_calls": 0, "subagents": 0},
        }
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if loaded.get("version") == 1:
                self.data = loaded
        except (OSError, json.JSONDecodeError):
            pass

    def consume(self, **amounts: int) -> dict[str, Any]:
        for key, value in amounts.items():
            if key in self.data["used"]:
                self.data["used"][key] += max(0, int(value))
        self.save()
        return self.status()

    def status(self) -> dict[str, Any]:
        limits = self.data["limits"]
        used = self.data["used"]
        remaining = {k: max(0, int(limits[k]) - int(used.get(k, 0))) for k in used if k in limits}
        exceeded = [k for k, v in remaining.items() if v <= 0 and int(used.get(k, 0)) >= int(limits.get(k, 0))]
        elapsed = max(0, int(time.time()) - int(self.data["started_at"]))
        if elapsed >= int(limits.get("wall_seconds", 0)) > 0:
            exceeded.append("wall_seconds")
        return {**self.data, "remaining": remaining, "elapsed_seconds": elapsed,
                "exceeded": sorted(set(exceeded)), "allow_more_work": not bool(exceeded)}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
