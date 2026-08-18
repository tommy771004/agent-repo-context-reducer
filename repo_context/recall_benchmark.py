from __future__ import annotations

import pathlib
from typing import Any

from .context_planner import build_context
from .context_store import build_repository_context_store, iter_index_evidence
from .recall import recall_repository_context

SCHEMA = "repo-context-recall-benchmark/v1"


def _gold_keys(case: dict[str, Any]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for item in case.get("critical_evidence") or []:
        if isinstance(item, str):
            out.add((item, ""))
        elif isinstance(item, dict) and item.get("path"):
            out.add((str(item["path"]), str(item.get("symbol") or "")))
    return out


def _present_keys(items: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {(str(x.get("path") or ""), str(x.get("symbol") or x.get("name") or "")) for x in items if isinstance(x, dict) and x.get("path")}


def benchmark_context_recall(
    index: dict[str, Any],
    cases: list[dict[str, Any]],
    *,
    initial_budget: int = 1200,
    recall_budget: int = 1800,
    tokenizer: str = "native",
    tokenizer_model: str | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    total_gold = initial_hits = final_hits = 0
    false_filter = 0
    for number, case in enumerate(cases):
        if not isinstance(case, dict) or not case.get("query"):
            continue
        gold = _gold_keys(case)
        if not gold:
            continue
        budget = int(case.get("initial_budget") or initial_budget)
        task = str(case.get("task") or case["query"])
        context = build_context(
            index, task, budget=budget,
            session=f"recall-benchmark-{number}", max_files=int(case.get("max_files") or 3),
            max_symbols=int(case.get("max_symbols") or 3), tokenizer=tokenizer, tokenizer_model=tokenizer_model,
        )
        store = build_repository_context_store(index, context, session=f"recall-benchmark-{number}", persist=False)
        active = _present_keys(store.items("active", current_only=True))
        recallable = _present_keys(list(iter_index_evidence(index))) - active
        initial = len(gold & active)
        false_filter_case = len(gold - (active | recallable))
        recalled = recall_repository_context(
            index, str(case["query"]), store=store, session=f"recall-benchmark-{number}",
            budget=int(case.get("recall_budget") or recall_budget), top_k=int(case.get("top_k") or 6),
            tokenizer=tokenizer, tokenizer_model=tokenizer_model, persist=False,
        )
        final_active = _present_keys(store.items("active", current_only=True))
        final = len(gold & final_active)
        total_gold += len(gold); initial_hits += initial; final_hits += final; false_filter += false_filter_case
        rows.append({
            "name": str(case.get("name") or f"case-{number+1}"),
            "task": task,
            "query": case["query"],
            "critical_evidence_count": len(gold),
            "initial_hits": initial,
            "final_hits": final,
            "rehydrated_hits": max(0, final - initial),
            "missed_after_recall": len(gold) - final,
            "false_filter_count": false_filter_case,
            "recall_model_calls_added": int((recalled.get("metrics") or {}).get("model_calls_added", 0)),
            "recalled_count": int((recalled.get("metrics") or {}).get("recalled_count", 0)),
        })
    initial_rate = initial_hits / max(1, total_gold)
    final_rate = final_hits / max(1, total_gold)
    return {
        "schema": SCHEMA,
        "classification": "deterministic-critical-evidence-recall-benchmark",
        "cases": rows,
        "aggregate": {
            "critical_evidence_count": total_gold,
            "initial_critical_evidence_recall": round(initial_rate, 4),
            "final_critical_evidence_recall": round(final_rate, 4),
            "recall_gain": round(final_rate - initial_rate, 4),
            "missed_critical_evidence": total_gold - final_hits,
            "false_filter_count": false_filter,
            "false_filter_rate": round(false_filter / max(1, total_gold), 4),
            "model_calls_added_by_recall": sum(int(r["recall_model_calls_added"]) for r in rows),
        },
        "policy": "Measure whether reduced repository context can recover known critical evidence without adding model calls.",
    }
