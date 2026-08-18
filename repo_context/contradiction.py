from __future__ import annotations

import math
import re
import unicodedata
from typing import Any


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def normalize_identity_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", _clean_text(value)).lower()
    return re.sub(r"\s+", " ", text).strip()


def canonical_group_key(finding: dict[str, Any]) -> str:
    canonical = _clean_text(finding.get("canonicalKey") or finding.get("canonical_key"))
    if canonical:
        return f"canonical:{canonical}"
    return f"claim:{normalize_identity_text(finding.get('claim'))}"


def identity_key(finding: dict[str, Any]) -> str | None:
    canonical = _clean_text(finding.get("canonicalKey") or finding.get("canonical_key"))
    if canonical:
        return f"canonical:{canonical}"

    subject = normalize_identity_text(finding.get("subject"))
    predicate = normalize_identity_text(finding.get("predicate"))
    period = normalize_identity_text(finding.get("period"))
    unit = normalize_identity_text(finding.get("unit"))
    if not subject or not predicate:
        return None
    return f"tuple:{subject}|{predicate}|{period}|{unit}"


def comparable_assertion_value(value: Any) -> tuple[str, Any] | None:
    """Normalize scalar assertion values without inventing semantic equivalence."""
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        number = float(value)
        return ("number", int(number) if number.is_integer() else number)
    if isinstance(value, str) and value.strip():
        return ("string", normalize_identity_text(value))
    return None


def detect_contradictions(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        key = identity_key(finding)
        if key:
            buckets.setdefault(key, []).append(finding)

    contradictions: list[dict[str, Any]] = []
    for key, group in sorted(buckets.items()):
        if len(group) < 2:
            continue

        polarities = {
            normalize_identity_text(item.get("polarity"))
            for item in group
            if normalize_identity_text(item.get("polarity"))
        }
        values = {
            comparable_assertion_value(item.get("value"))
            for item in group
            if comparable_assertion_value(item.get("value")) is not None
        }

        reasons: list[str] = []
        if len(polarities) > 1:
            reasons.append("polarity disagreement")
        if len(values) > 1:
            reasons.append("value disagreement")
        if not reasons:
            continue

        contradictions.append({
            "key": key,
            "reasons": reasons,
            "claims": [
                {
                    "claim": item.get("claim"),
                    "evidence": item.get("evidence"),
                    "source": item.get("source"),
                    "confidence": item.get("confidence"),
                    "worker": item.get("_worker"),
                    "value": item.get("value"),
                    "unit": item.get("unit"),
                    "polarity": item.get("polarity"),
                    "reducer": item.get("reducer") if isinstance(item.get("reducer"), dict) else None,
                }
                for item in group
            ],
        })
    return contradictions
