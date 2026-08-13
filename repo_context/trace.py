from __future__ import annotations

import json
import pathlib
import time
import uuid
from typing import Any

from .storage import prepare_state_dir, state_dir


def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


class Trace:
    def __init__(self, root: pathlib.Path, run_id: str | None = None):
        self.root = root
        self.run_id = run_id or new_run_id()
        self.path = state_dir(root) / "runs" / f"{self.run_id}.jsonl"

    def event(self, kind: str, data: dict[str, Any]) -> None:
        prepare_state_dir(self.root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ts": time.time(), "run_id": self.run_id, "kind": kind, "data": data}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_trace(root: pathlib.Path, run_id: str) -> list[dict[str, Any]]:
    path = state_dir(root) / "runs" / f"{run_id}.jsonl"
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return rows


def replay_summary(root: pathlib.Path, run_id: str) -> dict[str, Any]:
    rows = read_trace(root, run_id)
    return {
        "run_id": run_id,
        "events": rows,
        "counts": {k: sum(1 for r in rows if r.get("kind") == k) for k in sorted({r.get("kind") for r in rows})},
        "note": "Replay is observational by default and does not re-execute tool or write operations.",
    }
