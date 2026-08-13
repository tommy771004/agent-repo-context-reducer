from __future__ import annotations

import pathlib
import time
from typing import Any

from .scanner import build_index
from .storage import load_index, save_index


def _public_index(index: dict[str, Any]) -> dict[str, Any]:
    # by_path is derived and needlessly duplicates every file in persistent JSON.
    out = {k: v for k, v in index.items() if k != "by_path"}
    symbols: list[dict[str, Any]] = []
    for f in out.get("files", []):
        for sym in f.get("symbol_details", []):
            symbols.append({"path": f["path"], **sym})
    out["symbols"] = symbols
    out["symbol_count"] = len(symbols)
    return out


def hydrate(index: dict[str, Any]) -> dict[str, Any]:
    out = dict(index)
    out["by_path"] = {f["path"]: f for f in out.get("files", [])}
    return out


def build_persistent(root: pathlib.Path | str, **kwargs: Any) -> dict[str, Any]:
    root = pathlib.Path(root).resolve()
    index = build_index(root, **kwargs)
    public = _public_index(index)
    path = save_index(root, public)
    return {"index": hydrate(public), "path": str(path), "mode": "built"}


def ensure_index(root: pathlib.Path | str, sync: bool = True, **kwargs: Any) -> dict[str, Any]:
    root = pathlib.Path(root).resolve()
    existing = load_index(root)
    if existing is None:
        if not sync:
            raise ValueError("No persistent index exists; run `repo-context index` first or omit --no-sync")
        return build_persistent(root, **kwargs)
    if not sync:
        return {"index": hydrate(existing), "path": str(root / ".repo-context" / "index.json"), "mode": "loaded"}
    previous_paths = {f["path"] for f in existing.get("files", [])}
    before = existing.get("indexed_at")
    result = build_persistent(root, **kwargs)
    current = result["index"]
    current_paths = {f["path"] for f in current.get("files", [])}
    stats = current.setdefault("sync_stats", {})
    stats.update({
        "refresh_mode": "source-parse-cache-aware; graph/ranking rebuilt",
        "previous_indexed_at": before,
        "synced_at": int(time.time()),
        "added_files": sorted(current_paths - previous_paths)[:100],
        "removed_files": sorted(previous_paths - current_paths)[:100],
        "cache_hits": current.get("stats", {}).get("cache_hits", 0),
        "reparsed_source_files": current.get("stats", {}).get("cache_misses", 0),
    })
    result["mode"] = "refreshed"
    return result


def index_status(root: pathlib.Path | str) -> dict[str, Any]:
    root = pathlib.Path(root).resolve()
    existing = load_index(root)
    if existing is None:
        return {"indexed": False, "root": str(root)}
    return {
        "indexed": True,
        "root": str(root),
        "indexed_at": existing.get("indexed_at"),
        "files": len(existing.get("files", [])),
        "symbols": existing.get("symbol_count", len(existing.get("symbols", []))),
        "edges": sum(len(v) for v in existing.get("graph", {}).get("edges", {}).values()),
        "workspaces": len(existing.get("workspaces", [])),
        "languages": existing.get("languages", {}),
        "index_version": existing.get("index_version"),
    }
