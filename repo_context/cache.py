from __future__ import annotations

import json
import pathlib
from typing import Any

from .storage import prepare_state_dir, state_dir

# Bump whenever the structural parsers change: cache keys are path+mtime+size, so an
# unchanged file would otherwise keep serving a summary produced by the previous parser.
CACHE_VERSION = 4

# Caches written by earlier releases. They are discarded rather than migrated, because a
# summary produced by an older parser is stale by definition after a version bump.
STALE_CACHE_FILES = ("summaries-v3.json", "summaries-v2.json")


class SummaryCache:
    def __init__(self, root: pathlib.Path, enabled: bool = True):
        self.enabled = enabled
        self.root = root.resolve()
        self.path = state_dir(self.root) / "cache" / f"summaries-v{CACHE_VERSION}.json"
        self.data: dict[str, Any] = {"version": CACHE_VERSION, "items": {}}
        self.dirty = False
        if enabled:
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if loaded.get("version") == CACHE_VERSION and isinstance(loaded.get("items"), dict):
                    self.data = loaded
            except (OSError, json.JSONDecodeError):
                pass

    def _stale_paths(self) -> list[pathlib.Path]:
        cache_dir = state_dir(self.root) / "cache"
        legacy_dir = self.root / ".repo-context-cache"
        return [d / name for d in (cache_dir, legacy_dir) for name in STALE_CACHE_FILES]

    def _discard_stale(self) -> None:
        for path in self._stale_paths():
            try:
                path.unlink()
            except OSError:
                continue
            try:
                path.parent.rmdir()
            except OSError:
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
            prepare_state_dir(self.root)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            tmp.replace(self.path)
            self._discard_stale()
        except OSError:
            pass
