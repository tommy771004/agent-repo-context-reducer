from __future__ import annotations

import json
import pathlib
import time
from typing import Any

from .storage import prepare_state_dir, state_dir


class ProviderHealth:
    def __init__(self, root: pathlib.Path):
        self.root = root
        self.path = state_dir(root) / "provider-health.json"
        self.data: dict[str, Any] = {"version": 1, "providers": {}}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if loaded.get("version") == 1:
                self.data = loaded
        except (OSError, json.JSONDecodeError):
            pass

    def record(self, provider_id: str, success: bool, latency_ms: float | None = None) -> None:
        p = self.data["providers"].setdefault(provider_id, {
            "attempts": 0, "successes": 0, "failures": 0, "latency_ms_total": 0.0,
            "latency_samples": 0, "last_success_at": None, "last_failure_at": None,
        })
        p["attempts"] += 1
        if success:
            p["successes"] += 1
            p["last_success_at"] = int(time.time())
        else:
            p["failures"] += 1
            p["last_failure_at"] = int(time.time())
        if latency_ms is not None:
            p["latency_ms_total"] += max(0.0, float(latency_ms))
            p["latency_samples"] += 1
        self.save()

    def summary(self, provider_id: str | None = None) -> dict[str, Any]:
        ids = [provider_id] if provider_id else sorted(self.data["providers"])
        out = {}
        for pid in ids:
            p = self.data["providers"].get(pid)
            if not p:
                continue
            attempts = int(p.get("attempts", 0))
            samples = int(p.get("latency_samples", 0))
            success_rate = None if attempts <= 0 else round(int(p.get("successes", 0)) / attempts, 4)
            avg_latency = None if samples <= 0 else round(float(p.get("latency_ms_total", 0)) / samples, 2)
            out[pid] = {**p, "success_rate": success_rate, "avg_latency_ms": avg_latency,
                        "healthy": None if attempts < 3 else bool(success_rate is not None and success_rate >= 0.5)}
        return out

    def score_penalty(self, provider_id: str) -> float:
        p = self.summary(provider_id).get(provider_id)
        if not p or p.get("success_rate") is None:
            return 0.0
        attempts = int(p.get("attempts", 0))
        if attempts < 3:
            return 0.0
        rate = float(p["success_rate"])
        return max(0.0, 1.0 - rate) * 20.0

    def save(self) -> None:
        prepare_state_dir(self.root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
