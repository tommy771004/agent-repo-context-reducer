from __future__ import annotations

import pathlib
from typing import Any

from .ledger import SessionLedger
from .ranking import query_terms, lexical_score


def evaluate_read(index: dict[str, Any], path: str, task: str, session: str = "default", requested: str = "full") -> dict[str, Any]:
    rel = pathlib.PurePosixPath(path).as_posix().lstrip("./")
    f = index.get("by_path", {}).get(rel)
    if not f:
        return {"allow": False, "decision": "deny", "reason": "file-not-indexed", "path": rel}
    terms = query_terms(task)
    relevance = lexical_score(f, terms)
    ledger = SessionLedger(pathlib.Path(index["root"]), session=session)
    # File-level structural fingerprint is deliberately not content identity; full/symbol reads are fingerprinted separately.
    if requested == "full":
        if relevance <= 0 and terms:
            return {
                "allow": False,
                "decision": "prefer-structure",
                "reason": "low-task-relevance",
                "path": rel,
                "relevance_score": relevance,
                "alternative": f"repo-context deps . {rel}",
                "note": "Policy guidance only; a Skill cannot technically block an agent's built-in Read tool.",
            }
        if f.get("lines", 0) > 400:
            return {
                "allow": False,
                "decision": "prefer-symbol",
                "reason": "large-file",
                "path": rel,
                "lines": f.get("lines"),
                "relevance_score": relevance,
                "symbols": [s.get("name") for s in f.get("symbol_details", [])[:20]],
                "note": "Read a relevant symbol before requesting the whole file.",
            }
    return {"allow": True, "decision": "allow", "path": rel, "relevance_score": relevance, "requested": requested}
