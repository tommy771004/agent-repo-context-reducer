from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

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

DEFAULT_FIELD_PRIORITY = (
    "summary",
    "decisions",
    "tests",
    "risks",
    "open_questions",
    "evidence",
    "targets",
    "constraints",
    "changed_files",
)


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


def _estimated_tokens(value: Any) -> int:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return estimate_tokens_from_bytes(len(encoded))


def _build_body(*, from_role: str, to_role: str, task: str, artifact_id: str | None,
                source_hash: str, source_tokens: int, reduced: dict[str, Any],
                budget: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": "repo-context-handoff/v1",
        "from": from_role,
        "to": to_role,
        "task": task,
        "artifact_id": artifact_id,
        "source_sha256": source_hash,
        "source_estimated_tokens": source_tokens,
        "handoff": reduced,
        "provenance": {"method": "deterministic-key-selection", "lossy": True},
    }
    if budget is not None:
        body["budget"] = budget
    return body


def _select_to_budget(reduced: dict[str, Any], *, from_role: str, to_role: str, task: str,
                      artifact_id: str | None, source_hash: str, source_tokens: int,
                      token_budget: int, preserve_fields: Iterable[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    preserve = [f for f in preserve_fields if f in reduced]
    priority = list(dict.fromkeys([*preserve, *DEFAULT_FIELD_PRIORITY, *reduced.keys()]))
    selected: dict[str, Any] = {}
    dropped: list[str] = []

    budget_meta = {
        "target_estimated_tokens": token_budget,
        "estimated_tokens": 0,
        "overflow": False,
        "dropped_keys": dropped,
        "preserved_fields": preserve,
    }

    for field in priority:
        if field not in reduced or field in selected:
            continue
        candidate = {**selected, field: reduced[field]}
        candidate_body = _build_body(
            from_role=from_role,
            to_role=to_role,
            task=task,
            artifact_id=artifact_id,
            source_hash=source_hash,
            source_tokens=source_tokens,
            reduced=candidate,
            budget=budget_meta,
        )
        estimated = _estimated_tokens(candidate_body)
        if estimated <= token_budget or field in preserve:
            selected[field] = reduced[field]
            if estimated > token_budget and field in preserve:
                budget_meta["overflow"] = True
        else:
            dropped.append(field)

    final_body = _build_body(
        from_role=from_role,
        to_role=to_role,
        task=task,
        artifact_id=artifact_id,
        source_hash=source_hash,
        source_tokens=source_tokens,
        reduced=selected,
        budget=budget_meta,
    )
    budget_meta["estimated_tokens"] = _estimated_tokens(final_body)
    if budget_meta["estimated_tokens"] > token_budget:
        budget_meta["overflow"] = True
        budget_meta["overflow_reason"] = "preserved fields or fixed metadata exceed target"
    return selected, budget_meta


def reduce_handoff(payload: Any, *, from_role: str, to_role: str, task: str = "",
                   artifact_id: str | None = None, max_items: int = 12, max_chars: int = 1600,
                   token_budget: int | None = None,
                   preserve_fields: Iterable[str] = ("summary", "tests", "risks", "open_questions")) -> dict[str, Any]:
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        if not isinstance(payload, str)
        else payload.encode("utf-8")
    )
    source_tokens = estimate_tokens_from_bytes(len(encoded))
    source_hash = hashlib.sha256(encoded).hexdigest()
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
        reduced["summary"] = _bounded(payload, max_items=min(6, max_items), max_chars=min(600, max_chars))

    budget_meta = None
    if token_budget is not None:
        if token_budget <= 0:
            raise ValueError("token_budget must be positive")
        reduced, budget_meta = _select_to_budget(
            reduced,
            from_role=from_role,
            to_role=to_role,
            task=task,
            artifact_id=artifact_id,
            source_hash=source_hash,
            source_tokens=source_tokens,
            token_budget=token_budget,
            preserve_fields=preserve_fields,
        )

    body = _build_body(
        from_role=from_role,
        to_role=to_role,
        task=task,
        artifact_id=artifact_id,
        source_hash=source_hash,
        source_tokens=source_tokens,
        reduced=reduced,
        budget=budget_meta,
    )
    body["estimated_tokens"] = _estimated_tokens(body)
    body["estimated_reduction_ratio"] = round(1 - (body["estimated_tokens"] / max(1, source_tokens)), 4)
    if budget_meta is not None:
        body["budget"]["estimated_tokens"] = body["estimated_tokens"]
        if body["estimated_tokens"] > token_budget:
            body["budget"]["overflow"] = True
    return body
