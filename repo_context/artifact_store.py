from __future__ import annotations

import hashlib
import json
import pathlib
import time
import uuid
from typing import Any

from .storage import prepare_state_dir, state_dir
from .util import estimate_tokens_from_bytes


class ArtifactStore:
    def __init__(self, root: pathlib.Path | str):
        self.root = pathlib.Path(root).resolve()
        self.dir = state_dir(self.root) / "artifacts"

    def _path(self, artifact_id: str) -> pathlib.Path:
        if not artifact_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in artifact_id):
            raise ValueError("Invalid artifact id")
        return self.dir / f"{artifact_id}.json"

    @staticmethod
    def _encoded(value: Any) -> bytes:
        if isinstance(value, str):
            return value.encode("utf-8")
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def put(self, value: Any, *, kind: str = "agent-output", producer: str = "unknown",
            metadata: dict[str, Any] | None = None, artifact_id: str | None = None) -> dict[str, Any]:
        raw = self._encoded(value)
        digest = hashlib.sha256(raw).hexdigest()
        aid = artifact_id or f"a-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        record = {
            "schema": "repo-context-artifact/v1",
            "id": aid,
            "kind": kind,
            "producer": producer,
            "created_at": int(time.time()),
            "sha256": digest,
            "bytes": len(raw),
            "estimated_tokens": estimate_tokens_from_bytes(len(raw)),
            "metadata": metadata or {},
            "payload": value,
        }
        prepare_state_dir(self.root)
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._path(aid)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(path)
        return self.view(aid)

    def get(self, artifact_id: str) -> dict[str, Any]:
        path = self._path(artifact_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"Artifact not found: {artifact_id}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Corrupt artifact: {artifact_id}") from exc

    def view(self, artifact_id: str, include_payload: bool = False) -> dict[str, Any]:
        record = self.get(artifact_id)
        out = {k: v for k, v in record.items() if k != "payload"}
        payload = record.get("payload")
        if include_payload:
            out["payload"] = payload
        elif isinstance(payload, dict):
            out["payload_keys"] = sorted(str(k) for k in payload.keys())[:40]
        elif isinstance(payload, list):
            out["payload_items"] = len(payload)
        elif isinstance(payload, str):
            out["preview"] = payload[:280] + ("…" if len(payload) > 280 else "")
        return out

    def remove(self, artifact_id: str) -> dict[str, Any]:
        path = self._path(artifact_id)
        try:
            path.unlink()
        except FileNotFoundError as exc:
            raise ValueError(f"Artifact not found: {artifact_id}") from exc
        return {"id": artifact_id, "removed": True, "path": str(path)}

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.dir.exists():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(self.dir.glob("*.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)[:max(1, limit)]:
            try:
                items.append(self.view(path.stem))
            except (OSError, ValueError):
                continue
        return items
