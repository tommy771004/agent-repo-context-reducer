from __future__ import annotations

from typing import Any


RISK_TERMS: dict[str, tuple[int, tuple[str, ...]]] = {
    "security": (3, ("security", "vulnerability", "auth", "authentication", "authorization", "oauth", "credential", "secret", "資安", "驗證", "授權", "憑證")),
    "money": (3, ("payment", "billing", "invoice", "refund", "charge", "money", "付款", "金流", "帳務", "退款")),
    "data": (3, ("database migration", "schema migration", "drop table", "delete data", "production database", "資料庫遷移", "刪除資料", "正式資料庫")),
    "production": (3, ("production", "deploy", "deployment", "release", "rollback", "正式環境", "部署", "上線")),
    "public-contract": (2, ("public api", "breaking change", "backward compatibility", "api contract", "公開 api", "破壞性變更", "向後相容")),
    "broad-blast-radius": (2, ("entire project", "whole project", "across the repo", "architecture", "migration", "rewrite", "整個專案", "全專案", "架構", "遷移", "重寫")),
    "destructive": (4, ("rm -rf", "reset --hard", "force push", "truncate", "drop database", "刪庫", "強制推送")),
}

AMBIGUITY_TERMS = (
    "maybe", "perhaps", "somehow", "random", "sometimes", "intermittent", "unknown", "not sure", "unclear",
    "偶爾", "隨機", "有時候", "不確定", "不清楚", "可能", "莫名",
)

NOVELTY_TERMS = (
    "from scratch", "novel", "new architecture", "redesign", "greenfield", "new pattern", "invent",
    "從零", "全新架構", "重新設計", "新模式", "自行設計",
)


def classify_risk(task: str, task_type: str | None = None) -> dict[str, Any]:
    """Deterministic risk/ambiguity heuristic used for routing, never as a safety guarantee."""
    text = task.lower().strip()
    score = 0
    signals: list[str] = []
    for label, (points, terms) in RISK_TERMS.items():
        if any(term in text for term in terms):
            score += points
            signals.append(label)

    if task_type == "review" and any(term in text for term in ("security", "資安", "vulnerability")):
        score = max(score, 5)
    if task_type == "change-impact":
        score = max(score, 1)

    ambiguity_hits = sorted({term for term in AMBIGUITY_TERMS if term in text})
    novelty_hits = sorted({term for term in NOVELTY_TERMS if term in text})
    ambiguity_score = min(1.0, 0.22 * len(ambiguity_hits))
    novelty_score = min(1.0, 0.35 * len(novelty_hits))

    if novelty_hits:
        score += 1
        signals.append("novelty")

    if score <= 1:
        level = "low"
    elif score <= 4:
        level = "medium"
    elif score <= 7:
        level = "high"
    else:
        level = "critical"

    # Confidence means confidence in this routing classification, not confidence in the final answer.
    routing_confidence = round(max(0.35, min(0.98, 0.9 - ambiguity_score * 0.45 - novelty_score * 0.15)), 3)
    requires_escalation = level in {"high", "critical"} or ambiguity_score >= 0.44 or routing_confidence < 0.7

    return {
        "level": level,
        "score": score,
        "classification": "deterministic-risk-heuristic",
        "signals": sorted(set(signals)),
        "ambiguity": {"score": round(ambiguity_score, 3), "signals": ambiguity_hits},
        "novelty": {"score": round(novelty_score, 3), "signals": novelty_hits},
        "routing_confidence": routing_confidence,
        "requires_escalation": requires_escalation,
        "note": "Risk and ambiguity are routing heuristics, not a security review or correctness guarantee.",
    }
