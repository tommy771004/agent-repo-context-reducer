from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import time
from typing import Any

from .storage import prepare_state_dir, state_dir

STATE_SCHEMA = "repo-context-runtime-state/v1"


def _stable_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(_stable_json(value)).hexdigest()


def config_fingerprint(config: dict[str, Any]) -> str:
    """Fingerprint config without persisting its potentially sensitive values."""
    return fingerprint(config)


def _git(root: pathlib.Path, args: list[str]) -> subprocess.CompletedProcess[bytes] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=False, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def repository_runtime_identity(root: pathlib.Path | str) -> dict[str, Any]:
    """Return a bounded identity for detecting repository drift between resumes.

    The identity never materializes a full diff. For changed/untracked paths it records only
    status plus Git object identities for index/working content.
    """
    repo = pathlib.Path(root).resolve()
    head = _git(repo, ["rev-parse", "HEAD"])
    if head is None or head.returncode != 0:
        return {
            "classification": "runtime-repository-identity",
            "git_available": False,
            "root": str(repo),
            "fingerprint": None,
            "drift_detection": "unavailable-without-git",
        }
    commit = head.stdout.decode("utf-8", errors="replace").strip()
    status = _git(repo, ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "."])
    rows: list[dict[str, Any]] = []
    if status is not None and status.returncode == 0:
        chunks = status.stdout.split(b"\x00")
        i = 0
        while i < len(chunks):
            raw = chunks[i]
            i += 1
            if not raw:
                continue
            text = raw.decode("utf-8", errors="replace")
            code = text[:2]
            rel = text[3:] if len(text) >= 4 else text[2:].lstrip()
            # Rename/copy porcelain v1 -z emits an additional source path entry. The
            # destination path is still sufficient for content identity; consume source.
            source_rel = None
            if ("R" in code or "C" in code) and i < len(chunks) and chunks[i]:
                source_rel = chunks[i].decode("utf-8", errors="replace")
                i += 1
            index_blob = None
            if not code.startswith("??") and "D" not in code[:1]:
                index = _git(repo, ["ls-files", "-s", "--", rel])
                if index is not None and index.returncode == 0 and index.stdout:
                    parts = index.stdout.decode("utf-8", errors="replace").split()
                    if len(parts) >= 2:
                        index_blob = parts[1]
            working_blob = None
            path = repo / rel
            if path.is_file():
                blob = _git(repo, ["hash-object", "--", rel])
                if blob is not None and blob.returncode == 0:
                    working_blob = blob.stdout.decode("utf-8", errors="replace").strip() or None
            rows.append({"path": rel, "status": code, "index_blob": index_blob, "working_blob": working_blob, "source_path": source_rel})
    payload = {"commit": commit, "changes": rows}
    return {
        "classification": "runtime-repository-identity",
        "git_available": True,
        "root": str(repo),
        "commit": commit,
        "dirty": bool(rows),
        "changed_path_count": len(rows),
        "fingerprint": fingerprint(payload),
        "drift_detection": "HEAD + changed path status + index/working Git blob identities",
    }


def checkpoint_path(root: pathlib.Path | str, run_id: str) -> pathlib.Path:
    return state_dir(pathlib.Path(root).resolve()) / "runtime-runs" / str(run_id) / "checkpoint.json"


def _checkpoint_dir(root: pathlib.Path | str, run_id: str) -> pathlib.Path:
    return checkpoint_path(root, run_id).parent


def _safe_run_id(run_id: str) -> str:
    value = str(run_id).strip()
    if not value or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for c in value):
        raise ValueError("invalid runtime run id")
    return value


class RuntimeCheckpointStore:
    def __init__(self, root: pathlib.Path | str, run_id: str):
        self.root = pathlib.Path(root).resolve()
        self.run_id = _safe_run_id(run_id)
        self.path = checkpoint_path(self.root, self.run_id)

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"Runtime checkpoint not found: {self.run_id}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Corrupt runtime checkpoint: {self.run_id}") from exc
        if data.get("schema") != STATE_SCHEMA:
            raise ValueError(f"Unsupported runtime checkpoint schema: {data.get('schema')}")
        return data

    def save(self, payload: dict[str, Any]) -> pathlib.Path:
        prepare_state_dir(self.root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = dict(payload)
        body["schema"] = STATE_SCHEMA
        body["run_id"] = self.run_id
        body["updated_at"] = int(time.time())
        tmp = self.path.with_suffix(f".tmp-{os.getpid()}")
        tmp.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")
        tmp.replace(self.path)
        return self.path

    def summary(self) -> dict[str, Any]:
        data = self.load()
        results = data.get("results") if isinstance(data.get("results"), dict) else {}
        return {
            "schema": STATE_SCHEMA,
            "run_id": self.run_id,
            "status": data.get("status"),
            "task": data.get("task"),
            "adapter": data.get("adapter"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "resume_count": int(data.get("resume_count", 0)),
            "completed_nodes": sorted(k for k, v in results.items() if isinstance(v, dict) and v.get("status") == "success"),
            "node_statuses": {k: v.get("status") for k, v in results.items() if isinstance(v, dict)},
            "config_sha256": data.get("config_sha256"),
            "repository_identity": data.get("repository_identity"),
            "path": str(self.path),
        }


def list_runtime_runs(root: pathlib.Path | str, limit: int = 50) -> list[dict[str, Any]]:
    repo = pathlib.Path(root).resolve()
    base = state_dir(repo) / "runtime-runs"
    if not base.exists():
        return []
    items: list[dict[str, Any]] = []
    paths = sorted(base.glob("*/checkpoint.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    for path in paths[:max(1, int(limit))]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("schema") != STATE_SCHEMA:
            continue
        items.append({
            "run_id": data.get("run_id"),
            "status": data.get("status"),
            "task": data.get("task"),
            "adapter": data.get("adapter"),
            "updated_at": data.get("updated_at"),
            "resume_count": int(data.get("resume_count", 0)),
            "path": str(path),
        })
    return items
