from __future__ import annotations

import json
from typing import Any

from .util import estimate_tokens_from_bytes


SCHEMA = "repo-context-synthesis-packet/v1"


def _tokens(value: Any) -> int:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return estimate_tokens_from_bytes(len(raw))


def _finding_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    reducer = item.get("reducer") if isinstance(item.get("reducer"), dict) else {}
    return (
        -float(item.get("confidence", 0.5)),
        -int(reducer.get("agreement_count", 1)),
        str(item.get("claim", "")),
    )


def build_synthesis_packet(reduction: dict[str, Any], *, max_estimated_tokens: int = 6000) -> dict[str, Any]:
    if max_estimated_tokens <= 0:
        raise ValueError("max_estimated_tokens must be positive")

    contradictions = list(reduction.get("contradictions") or [])
    findings = sorted(list(reduction.get("findings") or []), key=_finding_sort_key)
    reducer_stats = reduction.get("stats") if isinstance(reduction.get("stats"), dict) else {}

    packet = {
        "schema": SCHEMA,
        "findings": [],
        "contradictions": contradictions,
        "reducer_summary": {
            "input_workers": reducer_stats.get("worker_output_count"),
            "valid_findings": reducer_stats.get("valid_finding_count"),
            "duplicates_removed": reducer_stats.get("duplicate_count"),
            "malformed_count": reducer_stats.get("malformed_count"),
            "agreement_groups": reducer_stats.get("agreement_group_count"),
            "contradictions": reducer_stats.get("contradiction_count"),
        },
        "budget": {
            "target_estimated_tokens": max_estimated_tokens,
            "estimated_tokens": 0,
            "dropped_findings": 0,
            "overflow": False,
            "mandatory_sections": ["contradictions"],
        },
        "policy": {
            "ranking": "confidence-desc, agreement-desc, claim",
            "contradictions_preserved": True,
            "semantic_similarity_used": False,
        },
    }

    mandatory_tokens = _tokens(packet)
    if mandatory_tokens > max_estimated_tokens:
        packet["budget"]["estimated_tokens"] = mandatory_tokens
        packet["budget"]["dropped_findings"] = len(findings)
        packet["budget"]["overflow"] = True
        packet["budget"]["overflow_reason"] = "mandatory contradiction/metadata sections exceed target"
        return packet

    selected: list[dict[str, Any]] = []
    for finding in findings:
        candidate = {**packet, "findings": selected + [finding]}
        estimated = _tokens(candidate)
        if estimated <= max_estimated_tokens:
            selected.append(finding)

    packet["findings"] = selected
    packet["budget"]["dropped_findings"] = len(findings) - len(selected)
    packet["budget"]["estimated_tokens"] = _tokens(packet)
    return packet
