from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import time
from typing import Any

from .storage import state_dir
from .util import DEFAULT_IGNORE_DIRS, estimate_tokens_from_bytes, is_secret_path, safe_read_text

KNOWLEDGE_SUFFIXES = {".md", ".mdx", ".txt", ".rst"}
PREFERRED_PARTS = {"docs", "doc", "adr", "adrs", "architecture", "decisions", "design", "rfcs", "rfc"}
ROOT_NAMES = {"readme.md", "readme.mdx", "changelog.md", "architecture.md", "contributing.md"}


def _candidate(path: pathlib.Path, root: pathlib.Path) -> bool:
    rel = path.relative_to(root).as_posix()
    if is_secret_path(rel) or ".repo-context/" in rel or rel.startswith(".repo-context/"):
        return False
    if path.suffix.lower() not in KNOWLEDGE_SUFFIXES:
        return False
    parts = {p.lower() for p in path.relative_to(root).parts[:-1]}
    return path.name.lower() in ROOT_NAMES or bool(parts & PREFERRED_PARTS)


def build_knowledge_index(root: pathlib.Path | str, max_files: int = 1000, max_file_bytes: int = 512_000) -> dict[str, Any]:
    repo = pathlib.Path(root).resolve()
    docs: list[dict[str, Any]] = []
    for current, dirnames, filenames in os.walk(repo):
        current_path = pathlib.Path(current)
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORE_DIRS and not d.startswith(".")]
        for filename in filenames:
            if len(docs) >= max_files:
                break
            path = current_path / filename
            if not _candidate(path, repo):
                continue
            text, size, reason = safe_read_text(path, max_file_bytes)
            if text is None:
                continue
            headings = [m.group(1).strip() for m in re.finditer(r"(?m)^#{1,4}\s+(.+)$", text)][:40]
            rel = path.relative_to(repo).as_posix()
            docs.append({
                "path": rel,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "bytes": size,
                "estimated_tokens": estimate_tokens_from_bytes(size),
                "headings": headings,
                "text": text,
            })
        if len(docs) >= max_files:
            break
    payload = {"schema": "repo-context-knowledge/v1", "root": str(repo), "indexed_at": int(time.time()), "documents": docs}
    out = state_dir(repo) / "knowledge.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"path": str(out), "documents": len(docs), "estimated_tokens_indexed": sum(d["estimated_tokens"] for d in docs)}


def _load(root: pathlib.Path) -> dict[str, Any] | None:
    path = state_dir(root) / "knowledge.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def search_knowledge(root: pathlib.Path | str, query: str, top_k: int = 8, budget: int = 1800, auto_index: bool = True) -> dict[str, Any]:
    repo = pathlib.Path(root).resolve()
    data = _load(repo)
    if data is None and auto_index:
        build_knowledge_index(repo)
        data = _load(repo)
    docs = (data or {}).get("documents", [])
    terms = [t.lower() for t in re.findall(r"[A-Za-z0-9_.$:/-]{2,}|[\u4e00-\u9fff]{2,}", query)]
    ranked: list[tuple[int, dict[str, Any]]] = []
    for doc in docs:
        hay = (doc.get("path", "") + "\n" + " ".join(doc.get("headings", [])) + "\n" + doc.get("text", "")).lower()
        score = sum(hay.count(term) for term in terms)
        if score:
            ranked.append((score, doc))
    ranked.sort(key=lambda x: (-x[0], x[1].get("path", "")))
    used = 0
    results: list[dict[str, Any]] = []
    for score, doc in ranked[:max(1, top_k) * 3]:
        text = doc.get("text", "")
        lower = text.lower()
        positions = [lower.find(term) for term in terms if lower.find(term) >= 0]
        pos = min(positions) if positions else 0
        snippet = text[max(0, pos - 220):pos + 900]
        tokens = estimate_tokens_from_bytes(len(snippet.encode("utf-8")))
        if results and used + tokens > budget:
            continue
        results.append({"path": doc.get("path"), "score": score, "headings": doc.get("headings", [])[:8], "snippet": snippet, "estimated_tokens": tokens})
        used += tokens
        if len(results) >= top_k or used >= budget:
            break
    return {
        "classification": "deterministic-lexical-knowledge-search",
        "query": query,
        "results": results,
        "budget": {"estimated_tokens": used, "limit": budget},
        "limitations": "Local fallback indexes documentation-like text only; it is not GraphRAG and does not infer a semantic knowledge graph.",
    }


def knowledge_status(root: pathlib.Path | str) -> dict[str, Any]:
    repo = pathlib.Path(root).resolve()
    data = _load(repo)
    if not data:
        return {"indexed": False, "path": str(state_dir(repo) / "knowledge.json")}
    return {"indexed": True, "path": str(state_dir(repo) / "knowledge.json"), "documents": len(data.get("documents", [])), "indexed_at": data.get("indexed_at")}
