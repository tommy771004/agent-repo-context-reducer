from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

from .util import estimate_tokens_from_bytes


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonicalize_external(provider: str, payload: Any) -> list[dict[str, Any]]:
    """Normalize external provider JSON into context blocks without inventing semantics.

    Accepted shapes:
      - list[dict]
      - {"results": list[dict]}
      - {"files": list[dict]}
      - {"symbols": list[dict]}
    Each block may contain path, symbol/name, content/text/summary, score.
    """
    if isinstance(payload, dict):
        if isinstance(payload.get("results"), list):
            items = payload["results"]
        elif isinstance(payload.get("symbols"), list):
            items = payload["symbols"]
        elif isinstance(payload.get("files"), list):
            items = payload["files"]
        else:
            items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError("external provider payload must be JSON object or array")

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in items:
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("path") or raw.get("file") or "").replace("\\", "/")
        symbol = str(raw.get("symbol") or raw.get("name") or "")
        content = raw.get("content")
        if content is None:
            content = raw.get("text")
        if content is None:
            content = raw.get("summary")
        content = "" if content is None else str(content)
        fp = _fingerprint(content) if content else ""
        key = (path, symbol, fp)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "provider": provider,
            "path": path or None,
            "symbol": symbol or None,
            "content": content or None,
            "fingerprint": fp or None,
            "estimated_tokens": estimate_tokens_from_bytes(len(content.encode("utf-8"))) if content else 0,
            "provider_score": raw.get("score"),
            "provenance": raw.get("provenance") or {"provider": provider},
        })
    return out


def load_external_file(path: pathlib.Path, provider: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return canonicalize_external(provider, payload)


def deduplicate_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Exact/canonical identity dedup only; no semantic merge claims."""
    out: list[dict[str, Any]] = []
    seen_fp: set[str] = set()
    seen_identity: set[tuple[str, str]] = set()
    for block in blocks:
        fp = str(block.get("fingerprint") or "")
        identity = (str(block.get("path") or ""), str(block.get("symbol") or ""))
        if fp and fp in seen_fp:
            continue
        if identity != ("", "") and identity in seen_identity and not fp:
            continue
        if fp:
            seen_fp.add(fp)
        if identity != ("", ""):
            seen_identity.add(identity)
        out.append(block)
    return out
