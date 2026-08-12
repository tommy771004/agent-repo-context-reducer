from __future__ import annotations

CONCEPTS = {
    "login": ["auth", "authentication", "session", "token", "jwt", "cookie", "credential", "refresh", "signin", "sign-in"],
    "登入": ["auth", "authentication", "session", "token", "jwt", "cookie", "credential", "refresh", "登入", "驗證"],
    "payment": ["checkout", "billing", "order", "transaction", "stripe", "refund", "invoice"],
    "付款": ["payment", "checkout", "billing", "order", "transaction", "stripe", "refund", "訂單"],
    "database": ["db", "repository", "storage", "sql", "orm", "entity", "model", "migration"],
    "資料庫": ["database", "db", "repository", "storage", "sql", "orm", "entity", "model"],
    "performance": ["latency", "slow", "cache", "memory", "cpu", "n+1", "query"],
    "效能": ["performance", "latency", "slow", "cache", "memory", "cpu", "query"],
}


def expand_terms(terms: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        for value in [term, *CONCEPTS.get(term.lower(), [])]:
            value = value.lower()
            if value not in seen:
                seen.add(value)
                out.append(value)
    return out[:80]
