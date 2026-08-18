from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

from .filter_engine import stable_fingerprint
from .util import estimate_tokens_from_bytes
from .trust_boundary import classify_untrusted_text


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _support_record(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": block.get("provider"),
        "path": block.get("path"),
        "symbol": block.get("symbol"),
        "provenance": block.get("provenance"),
        "provider_score": block.get("provider_score"),
    }


def _unique_support(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        key = stable_fingerprint(record)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _merge_blocks(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge duplicate content while aggregating every provider/source provenance record."""
    merged = dict(existing)
    support = []
    old_support = existing.get("support") if isinstance(existing.get("support"), dict) else {}
    new_support = incoming.get("support") if isinstance(incoming.get("support"), dict) else {}
    support.extend(x for x in (old_support.get("records") or []) if isinstance(x, dict))
    if not support:
        support.append(_support_record(existing))
    support.extend(x for x in (new_support.get("records") or []) if isinstance(x, dict))
    if not new_support.get("records"):
        support.append(_support_record(incoming))
    support = _unique_support(support)
    providers = sorted({str(x.get("provider")) for x in support if x.get("provider")})
    locations = sorted({
        f"{x.get('path') or ''}#{x.get('symbol') or ''}".rstrip("#")
        for x in support
        if x.get("path") or x.get("symbol")
    })
    occurrence_count = int(old_support.get("occurrence_count", 1)) + int(new_support.get("occurrence_count", 1))
    merged["support"] = {
        "schema": "repo-context-dedup-support/v1",
        "occurrence_count": occurrence_count,
        "provider_count": len(providers),
        "providers": providers,
        "location_count": len(locations),
        "locations": locations,
        "records": support,
        "provenance_preserved": True,
    }
    # Keep the highest provider score as the representative when numeric.
    scores = [x for x in (existing.get("provider_score"), incoming.get("provider_score")) if isinstance(x, (int, float))]
    if scores:
        merged["provider_score"] = max(scores)
    return merged


def canonicalize_external(provider: str, payload: Any) -> list[dict[str, Any]]:
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
    by_key: dict[tuple[str, str, str], int] = {}
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
        block = {
            "provider": provider,
            "path": path or None,
            "symbol": symbol or None,
            "content": content or None,
            "fingerprint": fp or None,
            "estimated_tokens": estimate_tokens_from_bytes(len(content.encode("utf-8"))) if content else 0,
            "provider_score": raw.get("score"),
            "provenance": raw.get("provenance") or {"provider": provider},
            "trust": classify_untrusted_text(content, source=f"provider:{provider}"),
        }
        block["support"] = {
            "schema": "repo-context-dedup-support/v1",
            "occurrence_count": 1,
            "provider_count": 1,
            "providers": [provider],
            "location_count": 1 if path or symbol else 0,
            "locations": [f"{path}#{symbol}".rstrip("#")] if path or symbol else [],
            "records": [_support_record(block)],
            "provenance_preserved": True,
        }
        key = (path, symbol, fp)
        if key in by_key:
            pos = by_key[key]
            out[pos] = _merge_blocks(out[pos], block)
            continue
        by_key[key] = len(out)
        out.append(block)
    return out


def load_external_file(path: pathlib.Path, provider: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return canonicalize_external(provider, payload)


def deduplicate_blocks(
    blocks: list[dict[str, Any]],
    *,
    return_stats: bool = False,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], dict[str, Any]]:
    """Deduplicate exact external content without discarding support provenance.

    Equal non-empty content merges only when path/symbol identity also matches. When a
    provider supplies no location, exact content may merge because no stronger identity is
    available. The representative keeps an explicit support aggregate so content tokens
    shrink without erasing provider/source lineage.
    """
    out: list[dict[str, Any]] = []
    positions: dict[tuple[str, ...], int] = {}
    input_count = 0
    merged_count = 0
    for raw in blocks:
        if not isinstance(raw, dict):
            continue
        input_count += 1
        block = dict(raw)
        fp = str(block.get("fingerprint") or "")
        identity = (str(block.get("path") or ""), str(block.get("symbol") or ""))
        if fp and identity != ("", ""):
            key = ("content+identity", fp, *identity)
        elif fp:
            key = ("content", fp)
        elif identity != ("", ""):
            key = ("identity", *identity)
        else:
            key = ("object", stable_fingerprint(block))
        if key in positions:
            pos = positions[key]
            out[pos] = _merge_blocks(out[pos], block)
            merged_count += 1
            continue
        positions[key] = len(out)
        if not isinstance(block.get("support"), dict):
            block["support"] = {
                "schema": "repo-context-dedup-support/v1",
                "occurrence_count": 1,
                "provider_count": 1 if block.get("provider") else 0,
                "providers": [block.get("provider")] if block.get("provider") else [],
                "location_count": 1 if any(identity) else 0,
                "locations": [f"{identity[0]}#{identity[1]}".rstrip("#")] if any(identity) else [],
                "records": [_support_record(block)],
                "provenance_preserved": True,
            }
        out.append(block)
    stats = {
        "input_blocks": input_count,
        "output_blocks": len(out),
        "duplicates_merged": merged_count,
        "provenance_preserved": True,
        "merge_authority": "exact-content-plus-location-identity; content-only only when location is absent",
    }
    return (out, stats) if return_stats else out
