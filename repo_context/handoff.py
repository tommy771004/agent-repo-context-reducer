from __future__ import annotations

import hashlib
import json
from typing import Any

from .util import estimate_tokens_from_bytes

KEY_ALIASES = {
    "summary": ("summary", "result", "conclusion"),
    "decisions": ("decisions", "decision"),
    "evidence": ("evidence", "findings", "facts"),
    "targets": ("targets", "symbols", "files", "relevant_files"),
    "constraints": ("constraints", "requirements", "guardrails"),
    "open_questions": ("open_questions", "questions", "unknowns", "unresolved"),
    "changed_files": ("changed_files", "changes", "modified_files"),
    "tests": ("tests", "test_results", "verification"),
    "risks": ("risks", "warnings", "concerns"),
}


def _bounded(value: Any, max_items: int = 12, max_chars: int = 1600) -> Any:
    if isinstance(value, str):
        return value[:max_chars] + ("…" if len(value) > max_chars else "")
    if isinstance(value, list):
        return [_bounded(v, max_items=max_items, max_chars=max_chars) for v in value[:max_items]]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k in list(value)[:max_items]:
            out[str(k)] = _bounded(value[k], max_items=max_items, max_chars=max_chars)
        return out
    return value


def reduce_handoff(payload: Any, *, from_role: str, to_role: str, task: str = "",
                   artifact_id: str | None = None, max_items: int = 12, max_chars: int = 1600) -> dict[str, Any]:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8") if not isinstance(payload, str) else payload.encode("utf-8")
    source_tokens = estimate_tokens_from_bytes(len(encoded))
    reduced: dict[str, Any] = {}

    if isinstance(payload, dict):
        lowered = {str(k).lower(): v for k, v in payload.items()}
        for canonical, aliases in KEY_ALIASES.items():
            for alias in aliases:
                if alias in lowered:
                    reduced[canonical] = _bounded(lowered[alias], max_items=max_items, max_chars=max_chars)
                    break
    else:
        reduced["summary"] = _bounded(str(payload), max_items=max_items, max_chars=max_chars)

    if not reduced.get("summary") and isinstance(payload, dict):
        # Preserve a compact deterministic preview when no conventional handoff keys exist.
        reduced["summary"] = _bounded(payload, max_items=min(6, max_items), max_chars=min(600, max_chars))

    body = {
        "schema": "repo-context-handoff/v1",
        "from": from_role,
        "to": to_role,
        "task": task,
        "artifact_id": artifact_id,
        "source_sha256": hashlib.sha256(encoded).hexdigest(),
        "source_estimated_tokens": source_tokens,
        "handoff": reduced,
        "provenance": {"method": "deterministic-key-selection", "lossy": True},
    }
    reduced_bytes = len(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    body["estimated_tokens"] = estimate_tokens_from_bytes(reduced_bytes)
    body["estimated_reduction_ratio"] = round(1 - (body["estimated_tokens"] / max(1, source_tokens)), 4)
    return body
