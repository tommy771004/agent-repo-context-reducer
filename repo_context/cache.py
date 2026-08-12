from __future__ import annotations

import json
import pathlib
from typing import Any

CACHE_VERSION = 2


class SummaryCache:
    def __init__(self, root: pathlib.Path, enabled: bool = True):
        self.enabled = enabled
        self.path = root / ".repo-context-cache" / "summaries-v2.json"
        self.data: dict[str, Any] = {"version": CACHE_VERSION, "items": {}}
        self.dirty = False
        if enabled:
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if loaded.get("version") == CACHE_VERSION and isinstance(loaded.get("items"), dict):
                    self.data = loaded
            except (OSError, json.JSONDecodeError):
                pass

    def get(self, rel: str, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        item = self.data["items"].get(rel)
        if item and item.get("key") == key:
            return item.get("summary")
        return None

    def put(self, rel: str, key: str, summary: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self.data["items"][rel] = {"key": key, "summary": summary}
        self.dirty = True

    def save(self) -> None:
        if not self.enabled or not self.dirty:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass
