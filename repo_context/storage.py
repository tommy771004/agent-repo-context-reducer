from __future__ import annotations

import json
import pathlib
import time
from typing import Any

INDEX_VERSION = 1
STATE_IGNORE_PATTERNS = (".repo-context/", ".repo-context-cache/")


def state_dir(root: pathlib.Path) -> pathlib.Path:
    return root / ".repo-context"


def ensure_state_ignored(root: pathlib.Path) -> dict[str, Any]:
    """Best-effort protection against runtime state appearing in git status.

    The legacy .repo-context-cache/ entry is retained for users upgrading from
    pre-1.4 releases even though v1.4 stores cache data under .repo-context/.
    """
    root = root.resolve()
    ignore = root / ".gitignore"
    try:
        existing = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
        lines = {line.strip() for line in existing.splitlines()}
        missing = [p for p in STATE_IGNORE_PATTERNS if p not in lines and p.rstrip("/") not in lines]
        if not missing:
            return {"path": str(ignore), "changed": False, "added": []}
        prefix = "" if not existing or existing.endswith("\n") else "\n"
        block = prefix + "# agent-repo-context-reducer runtime state\n" + "\n".join(missing) + "\n"
        ignore.write_text(existing + block, encoding="utf-8")
        return {"path": str(ignore), "changed": True, "added": missing}
    except OSError as exc:
        return {"path": str(ignore), "changed": False, "added": [], "warning": str(exc)}


def prepare_state_dir(root: pathlib.Path) -> pathlib.Path:
    ensure_state_ignored(root)
    folder = state_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


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
    folder = prepare_state_dir(root)
    out = dict(index)
    out["index_version"] = INDEX_VERSION
    out["indexed_at"] = int(time.time())
    path = folder / "index.json"
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
