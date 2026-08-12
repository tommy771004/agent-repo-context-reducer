from __future__ import annotations

import json
import pathlib
import time
from typing import Any

from .storage import state_dir


class ContextLifecycle:
    """Tracks metadata only. It does not claim to remove tokens already sent to a model."""

    def __init__(self, root: pathlib.Path, session: str = "default"):
        self.root = root
        self.session = session
        self.path = state_dir(root) / "lifecycle" / f"{session}.json"
        self.data: dict[str, Any] = {"version": 1, "session": session, "items": {}}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if loaded.get("version") == 1:
                self.data = loaded
        except (OSError, json.JSONDecodeError):
            pass

    def touch(self, key: str, fingerprint: str, estimated_tokens: int, tier: str = "hot") -> None:
        now = int(time.time())
        old = self.data["items"].get(key)
        if old and old.get("fingerprint") != fingerprint:
            old["tier"] = "invalid"
            old["invalidated_at"] = now
        self.data["items"][key] = {
            "fingerprint": fingerprint, "estimated_tokens": int(estimated_tokens),
            "tier": tier, "last_accessed": now, "access_count": int((old or {}).get("access_count", 0)) + 1,
        }

    def classify(self, hot_seconds: int = 900, warm_seconds: int = 7200) -> dict[str, int]:
        now = int(time.time())
        counts = {"hot": 0, "warm": 0, "cold": 0, "invalid": 0}
        for item in self.data["items"].values():
            if item.get("tier") == "invalid":
                counts["invalid"] += 1
                continue
            age = now - int(item.get("last_accessed", 0))
            tier = "hot" if age <= hot_seconds else "warm" if age <= warm_seconds else "cold"
            item["tier"] = tier
            counts[tier] += 1
        return counts

    def evict(self, max_hot_tokens: int = 6000) -> dict[str, Any]:
        self.classify()
        items = self.data["items"]
        hot = [(k, v) for k, v in items.items() if v.get("tier") == "hot"]
        hot.sort(key=lambda kv: (int(kv[1].get("last_accessed", 0)), int(kv[1].get("access_count", 0))))
        total = sum(int(v.get("estimated_tokens", 0)) for _, v in hot)
        evicted = []
        for key, item in hot:
            if total <= max_hot_tokens:
                break
            item["tier"] = "warm"
            total -= int(item.get("estimated_tokens", 0))
            evicted.append(key)
        self.save()
        return {"max_hot_tokens": max_hot_tokens, "hot_tokens_after": total, "demoted_to_warm": evicted,
                "note": "Lifecycle is harness metadata; model context eviction requires runtime integration."}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
