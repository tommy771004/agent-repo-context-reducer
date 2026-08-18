from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from .tokenizer import count_tokens, get_tokenizer
from .filter_engine import deduplicate_exact_list
from .trust_boundary import classify_untrusted_text

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

HANDOFF_SET_LIKE_FIELDS = {"decisions", "evidence", "targets", "constraints", "open_questions", "changed_files", "tests", "risks"}

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


def _estimated_tokens(value: Any, *, tokenizer: str = "native", tokenizer_model: str | None = None) -> int:
    return count_tokens(value, tokenizer=tokenizer, model=tokenizer_model)


def _build_body(*, from_role: str, to_role: str, task: str, artifact_id: str | None,
                source_hash: str, source_tokens: int, reduced: dict[str, Any],
                budget: dict[str, Any] | None = None,
                filter_summary: dict[str, Any] | None = None) -> dict[str, Any]:
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
        "trust": classify_untrusted_text(
            json.dumps(reduced, ensure_ascii=False, separators=(",", ":"), default=str),
            source=f"agent-handoff:{from_role}",
        ),
    }
    if budget is not None:
        body["budget"] = budget
    if filter_summary is not None:
        body["filter_summary"] = filter_summary
    return body


def _select_to_budget(reduced: dict[str, Any], *, from_role: str, to_role: str, task: str,
                      artifact_id: str | None, source_hash: str, source_tokens: int,
                      token_budget: int, preserve_fields: Iterable[str],
                      tokenizer: str, tokenizer_model: str | None,
                      filter_summary: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    preserve = [f for f in preserve_fields if f in reduced]
    priority = list(dict.fromkeys([*preserve, *DEFAULT_FIELD_PRIORITY, *reduced.keys()]))
    selected: dict[str, Any] = {}
    dropped: list[str] = []

    estimator = get_tokenizer(tokenizer, model=tokenizer_model)
    budget_meta = {
        "target_estimated_tokens": token_budget,
        "estimated_tokens": 0,
        "overflow": False,
        "dropped_keys": dropped,
        "preserved_fields": preserve,
        "tokenizer": estimator.name,
        "tokenizer_exact": bool(estimator.exact),
        "tokenizer_model": tokenizer_model,
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
            filter_summary=filter_summary,
        )
        estimated = _estimated_tokens(candidate_body, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
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
        filter_summary=filter_summary,
    )
    budget_meta["estimated_tokens"] = _estimated_tokens(final_body, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
    if budget_meta["estimated_tokens"] > token_budget:
        budget_meta["overflow"] = True
        budget_meta["overflow_reason"] = "preserved fields or fixed metadata exceed target"
    return selected, budget_meta


def reduce_handoff(payload: Any, *, from_role: str, to_role: str, task: str = "",
                   artifact_id: str | None = None, max_items: int = 12, max_chars: int = 1600,
                   token_budget: int | None = None,
                   preserve_fields: Iterable[str] = ("summary", "tests", "risks", "open_questions"),
                   tokenizer: str = "native", tokenizer_model: str | None = None) -> dict[str, Any]:
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        if not isinstance(payload, str)
        else payload.encode("utf-8")
    )
    source_tokens = count_tokens(encoded.decode("utf-8", errors="replace"), tokenizer=tokenizer, model=tokenizer_model)
    source_hash = hashlib.sha256(encoded).hexdigest()
    reduced: dict[str, Any] = {}
    dedup_lists_seen = 0
    dedup_items_removed = 0

    def dedup_then_bound(value: Any, *, deduplicate: bool = False, item_limit: int = max_items, char_limit: int = max_chars) -> Any:
        nonlocal dedup_lists_seen, dedup_items_removed
        deduped = value
        if deduplicate and isinstance(value, list):
            dedup_lists_seen += 1
            deduped, removed = deduplicate_exact_list(value)
            dedup_items_removed += int(removed)
        return _bounded(deduped, max_items=item_limit, max_chars=char_limit)

    if isinstance(payload, dict):
        lowered = {str(k).lower(): v for k, v in payload.items()}
        for canonical, aliases in KEY_ALIASES.items():
            for alias in aliases:
                if alias in lowered:
                    reduced[canonical] = dedup_then_bound(lowered[alias], deduplicate=canonical in HANDOFF_SET_LIKE_FIELDS)
                    break
    else:
        reduced["summary"] = _bounded(str(payload), max_items=max_items, max_chars=max_chars)

    if not reduced.get("summary") and isinstance(payload, dict):
        reduced["summary"] = dedup_then_bound(payload, item_limit=min(6, max_items), char_limit=min(600, max_chars))

    filter_summary = {
        "schema": "repo-context-filter-summary/v1",
        "classification": "deterministic-handoff-filter-summary",
        "exact_duplicate_list_items_removed": dedup_items_removed,
        "lists_scanned": dedup_lists_seen,
        "merge_authority": "exact-json-equality-on-set-like-top-level-fields-only",
        "nested_sequences_preserved": True,
    }

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
            tokenizer=tokenizer,
            tokenizer_model=tokenizer_model,
            filter_summary=filter_summary,
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
        filter_summary=filter_summary,
    )
    estimator = get_tokenizer(tokenizer, model=tokenizer_model)
    body["estimated_tokens"] = _estimated_tokens(body, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
    body["tokenizer"] = {"name": estimator.name, "exact": bool(estimator.exact), "model": tokenizer_model}
    body["estimated_reduction_ratio"] = round(1 - (body["estimated_tokens"] / max(1, source_tokens)), 4)
    if budget_meta is not None:
        body["budget"]["estimated_tokens"] = body["estimated_tokens"]
        if body["estimated_tokens"] > token_budget:
            body["budget"]["overflow"] = True
    return body
