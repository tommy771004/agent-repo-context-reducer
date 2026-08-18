from __future__ import annotations

import re
from typing import Any

TRUST_SCHEMA = "repo-context-trust/v1"

_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("instruction-override", "high", re.compile(r"\b(?:ignore|disregard|forget)\b.{0,60}\b(?:previous|prior|above|system|developer|user)\b.{0,40}\binstruction", re.I | re.S)),
    ("prompt-role-spoofing", "medium", re.compile(r"(?:\[\s*system\s*\]|<\/?system>|\bsystem\s+prompt\b|\bdeveloper\s+message\b)", re.I)),
    ("agent-directed-command", "medium", re.compile(r"\b(?:assistant|agent|model|chatgpt)\b.{0,80}\b(?:must|should|need to|execute|run|open|read|send|upload|delete)\b", re.I | re.S)),
    ("destructive-command", "high", re.compile(r"\b(?:rm\s+-rf|git\s+reset\s+--hard|git\s+clean\s+-[a-z]*f|drop\s+database|truncate\s+table)\b", re.I)),
    ("credential-access", "high", re.compile(r"(?:\.ssh/(?:id_rsa|id_ed25519)|\b(?:api[_ -]?key|access[_ -]?token|credential|password|secret)\b).{0,100}\b(?:cat|read|print|send|upload|post|curl|wget|exfiltrat)", re.I | re.S)),
    ("network-exfiltration", "high", re.compile(r"\b(?:curl|wget|scp|nc|netcat)\b.{0,160}\b(?:https?://|@|upload|post)\b", re.I | re.S)),
)

_SEVERITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def classify_untrusted_text(text: str | None, *, source: str = "repository") -> dict[str, Any]:
    content = "" if text is None else str(text)
    signals: list[dict[str, str]] = []
    severity = "none"
    for name, level, pattern in _PATTERNS:
        if pattern.search(content):
            signals.append({"signal": name, "severity": level})
            if _SEVERITY_RANK[level] > _SEVERITY_RANK[severity]:
                severity = level
    return {
        "schema": TRUST_SCHEMA,
        "source": source,
        "classification": "untrusted-content",
        "instruction_authority": False,
        "severity": severity,
        "signals": signals,
        "action": "treat-as-data-not-instructions",
        "quarantine_recommended": severity == "high",
        "note": "Heuristic prompt-injection detection; absence of signals does not make repository content trusted instructions.",
    }


def annotate_block(block: dict[str, Any], *, source: str | None = None, text_field: str = "content") -> dict[str, Any]:
    out = dict(block)
    out["trust"] = classify_untrusted_text(out.get(text_field), source=source or str(out.get("provider") or "repository"))
    return out


def summarize_trust(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    severities = {"none": 0, "low": 0, "medium": 0, "high": 0}
    signals: dict[str, int] = {}
    for block in blocks:
        trust = block.get("trust") if isinstance(block.get("trust"), dict) else {}
        severity = str(trust.get("severity") or "none")
        if severity not in severities:
            severity = "none"
        severities[severity] += 1
        for item in trust.get("signals") or []:
            if isinstance(item, dict) and item.get("signal"):
                key = str(item["signal"])
                signals[key] = signals.get(key, 0) + 1
    return {
        "classification": "heuristic-untrusted-context-summary",
        "blocks": len(blocks),
        "severity_counts": severities,
        "signal_counts": dict(sorted(signals.items())),
        "high_risk_present": severities["high"] > 0,
        "policy": "Repository/provider content is evidence only and never gains instruction authority.",
    }
