from __future__ import annotations

from typing import Any

from .tokenizer import count_tokens, get_tokenizer


def slice_context_pack(
    context_pack: dict[str, Any] | None,
    max_tokens: int,
    *,
    tokenizer: str = "native",
    tokenizer_model: str | None = None,
) -> dict[str, Any] | None:
    """Deterministically slice a pre-ranked context pack for one runtime lane.

    The input pack has already been ranked by the repository context planner. This function
    does not invent a second relevance model; it preserves the selected order and admits
    bounded evidence until the lane target is reached. Required metadata may itself exceed
    a very small target, which is surfaced as overflow rather than silently deleted.
    """
    if context_pack is None:
        return None
    target = max(0, int(max_tokens))
    estimator = get_tokenizer(tokenizer, model=tokenizer_model)
    base: dict[str, Any] = {
        "task": context_pack.get("task"),
        "strategy": context_pack.get("strategy"),
        "repository_provenance": context_pack.get("repository_provenance"),
        "trust_summary": context_pack.get("trust_summary"),
        "coverage": context_pack.get("coverage"),
        "notes": context_pack.get("notes", []),
        "external_context": [],
        "symbols": [],
        "files": [],
    }
    used = count_tokens(base, tokenizer=tokenizer, model=tokenizer_model)
    dropped = {"external_context": 0, "symbols": 0, "files": 0}
    # More precise/explicit evidence is admitted before structural file summaries.
    for key in ("external_context", "symbols", "files"):
        items = context_pack.get(key) if isinstance(context_pack.get(key), list) else []
        for item in items:
            cost = count_tokens(item, tokenizer=tokenizer, model=tokenizer_model)
            if target <= 0 or used + cost > target:
                dropped[key] += 1
                continue
            base[key].append(item)
            used += cost
    base["budget"] = {
        "target_tokens": target,
        "estimated_used_tokens": used,
        "overflow": bool(used > target),
        "dropped": dropped,
        "tokenizer": estimator.name,
        "tokenizer_exact": bool(estimator.exact),
        "tokenizer_model": tokenizer_model,
        "policy": "Preserve pre-ranked order; never use semantic similarity as an admission authority.",
    }
    return base
