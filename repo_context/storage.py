from __future__ import annotations

import json
import pathlib
import time
from typing import Any

INDEX_VERSION = 1


def state_dir(root: pathlib.Path) -> pathlib.Path:
    return root / ".repo-context"


def index_path(root: pathlib.Path) -> pathlib.Path:
    return state_dir(root) / "index.json"


def load_index(root: pathlib.Path) -> dict[str, Any] | None:
    path = index_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("index_version") == INDEX_VERSION:
            return data
    except (OSError, json.JSONDecodeError):
        return None
    return None


def save_index(root: pathlib.Path, index: dict[str, Any]) -> pathlib.Path:
    folder = state_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    out = dict(index)
    out["index_version"] = INDEX_VERSION
    out["indexed_at"] = int(time.time())
    path = index_path(root)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
    return path


def remove_index(root: pathlib.Path) -> None:
    path = index_path(root)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
