from __future__ import annotations

import re
from typing import Any


def analyze_context_usage(context_pack: dict[str, Any], answer: str) -> dict[str, Any]:
    """Lexical attribution only; it does not inspect model attention."""
    lower = answer.lower()
    blocks = []
    for f in context_pack.get("files", []):
        ident = f.get("path", "")
        terms = [ident] + f.get("functions", []) + f.get("classes", []) + f.get("types", [])
        used = any(t and t.lower() in lower for t in terms)
        blocks.append({"kind": "file", "id": ident, "estimated_tokens": f.get("estimated_tokens", 0), "lexically_referenced": used})
    for s in context_pack.get("symbols", []):
        ident = f"{s.get('path')}#{s.get('name')}"
        terms = [s.get("name", ""), s.get("path", "")]
        used = any(t and t.lower() in lower for t in terms)
        blocks.append({"kind": "symbol", "id": ident, "estimated_tokens": s.get("estimated_tokens", 0), "lexically_referenced": used})
    total = sum(int(b["estimated_tokens"] or 0) for b in blocks)
    referenced = sum(int(b["estimated_tokens"] or 0) for b in blocks if b["lexically_referenced"])
    return {
        "blocks": blocks,
        "estimated_context_tokens": total,
        "lexically_attributed_tokens": referenced,
        "possible_dead_context_tokens": max(0, total - referenced),
        "classification": "heuristic-lexical-attribution",
        "warning": "Absence of lexical mention does not prove the model did not use a context block.",
    }
