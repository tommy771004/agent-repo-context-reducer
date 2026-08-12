from __future__ import annotations

import difflib
import json
import pathlib
import re
import time
from typing import Any

from .storage import state_dir


def _safe_session(session: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", session).strip(".-")
    return value or "default"


class SessionLedger:
    def __init__(self, root: pathlib.Path, session: str = "default"):
        self.root = root
        self.session = _safe_session(session)
        self.path = state_dir(root) / "sessions" / f"{self.session}.json"
        self.data: dict[str, Any] = {"version": 1, "session": self.session, "items": {}}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if loaded.get("version") == 1:
                self.data = loaded
        except (OSError, json.JSONDecodeError):
            pass

    def compare(self, key: str, fingerprint: str, content: str | None = None) -> dict[str, Any]:
        old = self.data["items"].get(key)
        if not old:
            return {"state": "new"}
        if old.get("fingerprint") == fingerprint:
            return {"state": "unchanged", "seen_at": old.get("seen_at")}
        result: dict[str, Any] = {"state": "changed", "previous_fingerprint": old.get("fingerprint")}
        if content is not None and old.get("content") is not None:
            diff = "\n".join(difflib.unified_diff(old["content"].splitlines(), content.splitlines(), fromfile="previous", tofile="current", lineterm=""))
            result["diff"] = diff
        return result

    def record(self, key: str, fingerprint: str, content: str | None = None) -> None:
        item: dict[str, Any] = {"fingerprint": fingerprint, "seen_at": int(time.time())}
        if content is not None and len(content.encode("utf-8")) <= 80_000:
            item["content"] = content
        self.data["items"][key] = item

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(self.path)
