from __future__ import annotations

import json
from typing import Any

from .contradiction import canonical_group_key, detect_contradictions
from .util import estimate_tokens_from_bytes


SCHEMA = "repo-context-fan-in/v1"


def _tokens(value: Any) -> int:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return estimate_tokens_from_bytes(len(raw))


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _confidence(value: Any) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return 0.5
    return n if 0.0 <= n <= 1.0 else 0.5


def _worker_name(payload: dict[str, Any], index: int) -> str:
    for key in ("worker", "producer", "agent", "from", "role"):
        value = _clean(payload.get(key))
        if value:
            return value
    if isinstance(payload.get("provenance"), dict):
        value = _clean(payload["provenance"].get("worker") or payload["provenance"].get("producer"))
        if value:
            return value
    return f"worker-{index + 1}"


def _candidate_items(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        return [payload]

    handoff = payload.get("handoff")
    if isinstance(handoff, dict):
        for key in ("findings", "evidence", "facts"):
            if isinstance(handoff.get(key), list):
                return list(handoff[key])

    for key in ("findings", "evidence", "facts"):
        if isinstance(payload.get(key), list):
            return list(payload[key])

    if any(key in payload for key in ("claim", "evidence", "source")):
        return [payload]
    return []


def _normalize_finding(raw: Any, *, worker: str, worker_index: int, item_index: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None, {
                "worker": worker,
                "worker_index": worker_index,
                "item_index": item_index,
                "reason": "empty evidence string",
                "finding": raw,
            }
        return {
            "claim": text,
            "evidence": text,
            "source": f"worker:{worker}",
            "source_kind": "worker-handoff",
            "confidence": 0.5,
            "_worker": worker,
        }, None

    if not isinstance(raw, dict):
        return None, {
            "worker": worker,
            "worker_index": worker_index,
            "item_index": item_index,
            "reason": "finding must be an object or non-empty string",
            "finding": raw,
        }

    claim = _clean(raw.get("claim") or raw.get("summary") or raw.get("fact"))
    evidence = _clean(raw.get("evidence") or raw.get("detail") or raw.get("support"))
    source = _clean(raw.get("source") or raw.get("path") or raw.get("file") or raw.get("url"))

    missing: list[str] = []
    if not claim:
        missing.append("claim")
    if not evidence:
        missing.append("evidence")
    if not source:
        missing.append("source")
    if missing:
        return None, {
            "worker": worker,
            "worker_index": worker_index,
            "item_index": item_index,
            "reason": f"missing required field(s): {', '.join(missing)}",
            "finding": raw,
        }

    finding = {
        **raw,
        "claim": claim,
        "evidence": evidence,
        "source": source,
        "confidence": _confidence(raw.get("confidence")),
        "_worker": worker,
    }
    canonical = _clean(raw.get("canonicalKey") or raw.get("canonical_key"))
    if canonical:
        finding["canonicalKey"] = canonical
    return finding, None


def reduce_worker_outputs(worker_outputs: list[Any], *, min_confidence: float = 0.0,
                          detect_conflicts: bool = True) -> dict[str, Any]:
    if not isinstance(worker_outputs, list):
        raise TypeError("worker_outputs must be a list")
    if not 0.0 <= float(min_confidence) <= 1.0:
        raise ValueError("min_confidence must be between 0 and 1")

    malformed: list[dict[str, Any]] = []
    valid: list[dict[str, Any]] = []
    extracted_count = 0

    for worker_index, payload in enumerate(worker_outputs):
        worker = _worker_name(payload, worker_index) if isinstance(payload, dict) else f"worker-{worker_index + 1}"
        items = _candidate_items(payload)
        if not items:
            malformed.append({
                "worker": worker,
                "worker_index": worker_index,
                "item_index": None,
                "reason": "worker output contains no findings/evidence",
                "finding": payload,
            })
            continue

        for item_index, raw in enumerate(items):
            extracted_count += 1
            finding, error = _normalize_finding(
                raw, worker=worker, worker_index=worker_index, item_index=item_index
            )
            if error:
                malformed.append(error)
                continue
            assert finding is not None
            if finding["confidence"] < min_confidence:
                malformed.append({
                    "worker": worker,
                    "worker_index": worker_index,
                    "item_index": item_index,
                    "reason": f"confidence below threshold {min_confidence}",
                    "finding": raw,
                })
                continue
            valid.append(finding)

    groups: dict[str, list[dict[str, Any]]] = {}
    for finding in valid:
        groups.setdefault(canonical_group_key(finding), []).append(finding)

    findings: list[dict[str, Any]] = []
    duplicate_count = 0
    agreement_group_count = 0
    max_agreement_count = 0

    def assertion_signature(item: dict[str, Any]) -> tuple[Any, ...]:
        polarity = _clean(item.get("polarity")).lower()
        value = item.get("value")
        has_numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
        if polarity or has_numeric:
            return ("structured", polarity or None, value if has_numeric else None)
        return ("unstructured",)

    for key, identity_group in groups.items():
        # canonicalKey identifies the fact, not necessarily the asserted side. When
        # structured value/polarity exists, contradictory sides must remain separate
        # findings so disagreement is not mislabeled as worker agreement.
        structured = any(assertion_signature(item)[0] == "structured" for item in identity_group)
        assertion_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        if structured:
            for item in identity_group:
                assertion_groups.setdefault(assertion_signature(item), []).append(item)
        else:
            assertion_groups[("unstructured",)] = identity_group

        for assertion_key, group in assertion_groups.items():
            ordered = sorted(
                group,
                key=lambda item: (-float(item.get("confidence", 0.5)), item.get("_worker", ""), item.get("source", "")),
            )
            best = dict(ordered[0])
            duplicate_count += max(0, len(group) - 1)
            agreement_count = len(group)
            if agreement_count > 1:
                agreement_group_count += 1
            max_agreement_count = max(max_agreement_count, agreement_count)

            workers = sorted({_clean(item.get("_worker")) for item in group if _clean(item.get("_worker"))})
            sources = sorted({_clean(item.get("source")) for item in group if _clean(item.get("source"))})
            best.pop("_worker", None)
            best["reducer"] = {
                "group_key": key,
                "assertion_key": list(assertion_key),
                "agreement_count": agreement_count,
                "supporting_workers": workers,
                "supporting_sources": sources,
            }
            findings.append(best)

    findings.sort(
        key=lambda item: (
            -float(item.get("confidence", 0.5)),
            -int(item.get("reducer", {}).get("agreement_count", 1)),
            item.get("claim", ""),
        )
    )

    contradictions = detect_contradictions(valid) if detect_conflicts else []
    compact = {"findings": findings, "contradictions": contradictions}
    before_tokens = _tokens(worker_outputs)
    after_tokens = _tokens(compact)

    return {
        "schema": SCHEMA,
        "findings": findings,
        "contradictions": contradictions,
        "malformed": malformed,
        "stats": {
            "worker_output_count": len(worker_outputs),
            "extracted_finding_count": extracted_count,
            "valid_finding_count": len(valid),
            "output_finding_count": len(findings),
            "malformed_count": len(malformed),
            "duplicate_count": duplicate_count,
            "agreement_group_count": agreement_group_count,
            "max_agreement_count": max_agreement_count,
            "contradiction_count": len(contradictions),
            "estimated_tokens_before": before_tokens,
            "estimated_tokens_after_reduction": after_tokens,
            "estimated_reduction_ratio": round(1 - (after_tokens / max(1, before_tokens)), 4),
        },
        "provenance": {
            "method": "deterministic-exact-or-canonical-grouping",
            "semantic_similarity_used": False,
            "lossy": True,
            "correctness_note": "A missed duplicate costs context; a false merge can destroy evidence, so fuzzy merge is intentionally disabled.",
        },
    }
