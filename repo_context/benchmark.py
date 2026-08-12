from __future__ import annotations

import json
import pathlib
from typing import Any

from .context_planner import build_context
from .indexer import ensure_index
from .util import estimate_tokens_from_bytes


def _raw_source_estimate(index: dict[str, Any]) -> int:
    return sum(estimate_tokens_from_bytes(int(f.get("bytes", 0))) for f in index.get("files", []))


def benchmark_tasks(root: pathlib.Path, tasks: list[dict[str, Any]], budget: int = 6000) -> dict[str, Any]:
    index = ensure_index(root, sync=True)["index"]
    raw = _raw_source_estimate(index)
    rows = []
    for i, task in enumerate(tasks):
        text = str(task.get("task", ""))
        pack = build_context(index, text, budget=budget, session=f"benchmark-{i}")
        selected_paths = {f.get("path") for f in pack.get("files", [])} | {s.get("path") for s in pack.get("symbols", [])}
        expected = set(task.get("expected_paths", []))
        recall = None if not expected else len(expected & selected_paths) / len(expected)
        used = int(pack["budget"]["estimated_used_tokens"])
        rows.append({
            "task": text, "raw_repository_token_estimate": raw, "context_token_estimate": used,
            "structural_reduction_ratio": None if raw <= 0 else round(1 - used / raw, 4),
            "selected_paths": sorted(p for p in selected_paths if p),
            "expected_path_recall": None if recall is None else round(recall, 4),
            "correctness_claim": False,
        })
    return {
        "tasks": rows,
        "metrics": {
            "token_estimator": "utf8-bytes/4",
            "correctness": "not-measured unless expected_paths are supplied; path recall is not answer correctness",
        },
    }


def load_tasks(path: pathlib.Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict) and x.get("task")]
    raise ValueError("benchmark task file must be a JSON array")
