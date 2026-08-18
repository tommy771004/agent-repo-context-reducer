from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA = "repo-context-context-evidence/v1"


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def logical_evidence_id(*, path: str, symbol: str | None = None, start_line: int | None = None, end_line: int | None = None) -> str:
    location = f"{path}#{symbol or ''}:{start_line or ''}-{end_line or ''}"
    return "ctx:" + _sha(location)[:20]


def make_context_evidence(
    *,
    kind: str,
    path: str,
    symbol: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    revision: str | None = None,
    revision_kind: str = "stat-fingerprint",
    content: str | None = None,
    assertion: dict[str, Any] | None = None,
    tier: str = "recallable",
    source: str = "repository",
) -> dict[str, Any]:
    """Create a repository-scoped evidence locator.

    The object is a control-plane record. Recallable entries intentionally do not need
    to carry source content; path/symbol/span are sufficient to rehydrate from the repo.
    """
    path = _norm(path)
    symbol = _norm(symbol) or None
    if not path:
        raise ValueError("context evidence requires a repository path")
    if tier not in {"active", "recallable", "rejected"}:
        raise ValueError("tier must be active, recallable, or rejected")
    content_sha = _sha(content) if isinstance(content, str) else None
    item: dict[str, Any] = {
        "schema": SCHEMA,
        "classification": "repository-context-evidence",
        "id": logical_evidence_id(path=path, symbol=symbol, start_line=start_line, end_line=end_line),
        "kind": kind,
        "source": source,
        "path": path,
        "tier": tier,
        "validity": "current",
        "revision": {"kind": revision_kind, "value": revision or ""},
    }
    if symbol:
        item["symbol"] = symbol
    if start_line is not None:
        item["start_line"] = int(start_line)
    if end_line is not None:
        item["end_line"] = int(end_line)
    if content_sha:
        item["content_sha256"] = content_sha
    if isinstance(assertion, dict) and assertion:
        item["assertion"] = {k: assertion[k] for k in ("subject", "predicate", "object", "value", "polarity") if k in assertion}
    return item


def _structured_side(item: dict[str, Any]) -> tuple[Any, ...] | None:
    assertion = item.get("assertion") if isinstance(item.get("assertion"), dict) else {}
    if not assertion:
        return None
    keys = ("subject", "predicate", "object", "value", "polarity")
    values = tuple(assertion.get(k) for k in keys)
    return values if any(v is not None for v in values) else None


def verify_context_evidence(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Deterministically compare repository evidence without semantic guessing."""
    if not isinstance(left, dict) or not isinstance(right, dict):
        return {"status": "unknown", "merge_authorized": False, "reason": "non-object-evidence"}
    if left.get("id") and right.get("id") and left.get("id") != right.get("id"):
        return {"status": "proven-different", "merge_authorized": False, "reason": "different-logical-location"}

    left_rev = ((left.get("revision") or {}).get("value") if isinstance(left.get("revision"), dict) else None) or None
    right_rev = ((right.get("revision") or {}).get("value") if isinstance(right.get("revision"), dict) else None) or None
    if left_rev and right_rev and left_rev != right_rev:
        return {"status": "revision-conflict", "merge_authorized": False, "reason": "same-location-different-revision"}

    left_side = _structured_side(left)
    right_side = _structured_side(right)
    if left_side is not None and right_side is not None and left_side != right_side:
        return {"status": "conflict", "merge_authorized": False, "reason": "different-structured-assertion"}

    lsha = left.get("content_sha256")
    rsha = right.get("content_sha256")
    if lsha and rsha:
        if lsha == rsha:
            return {"status": "proven-same", "merge_authorized": True, "reason": "same-location-revision-content-sha"}
        return {"status": "content-conflict", "merge_authorized": False, "reason": "same-location-different-content"}

    if left_side is not None and left_side == right_side:
        return {"status": "compatible", "merge_authorized": False, "reason": "same-structured-assertion-without-content-proof"}
    return {"status": "unknown", "merge_authorized": False, "reason": "insufficient-deterministic-evidence"}


def stable_evidence_fingerprint(item: dict[str, Any]) -> str:
    payload = {k: item.get(k) for k in ("id", "kind", "path", "symbol", "start_line", "end_line", "revision", "content_sha256", "assertion")}
    return _sha(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
