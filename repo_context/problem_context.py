from __future__ import annotations

import re
from typing import Any

from .ranking import query_terms, rank_files


SCHEMA = "repo-context-problem-context/v1"
_LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)、]|[（(]?[一二三四五六七八九十]+[)）、.])\s*(.+?)\s*$")


def _clean_problem(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip(" \t\r\n;；")


def derive_problem_requirements(task: str) -> list[dict[str, Any]]:
    """Preserve every explicit problem in a deterministic requirement ledger."""
    raw = str(task or "").strip()
    explicit: list[str] = []
    preamble: list[str] = []
    saw_explicit = False
    for line in raw.splitlines():
        match = _LIST_ITEM.match(line)
        if match:
            saw_explicit = True
            value = _clean_problem(match.group(1))
            if value:
                explicit.append(value)
        elif not saw_explicit and (value := _clean_problem(line)):
            preamble.append(value.rstrip("：:"))

    problems = explicit
    if not problems:
        segments = [_clean_problem(value) for value in re.split(r"[;；\n]+", raw)]
        problems = [value for value in segments if value]

    if len(problems) == 1 and "、" in problems[0]:
        # Preserve the action for compact Chinese problem lists such as
        # "修復登入、RWD、動畫問題" instead of producing noun-only fragments.
        match = re.match(r"^(.*?)(修復|改善|處理|檢查|解決|完成)\s*(.+)$", problems[0])
        if match:
            prefix = _clean_problem(match.group(1) + match.group(2))
            objects = [_clean_problem(value) for value in match.group(3).split("、")]
            if len([value for value in objects if value]) > 1:
                problems = [_clean_problem(f"{prefix} {value}") for value in objects if value]

    if not problems and raw:
        problems = [_clean_problem(raw)]

    seen: set[str] = set()
    requirements: list[dict[str, Any]] = []
    for problem in problems:
        normalized = problem.casefold()
        if not problem or normalized in seen:
            continue
        seen.add(normalized)
        query = _clean_problem(" ".join([*preamble, problem])) if explicit and preamble else problem
        requirements.append({
            "id": f"problem-{len(requirements) + 1:03d}",
            "text": problem,
            "query": query,
            "terms": query_terms(problem),
            "ranking_terms": query_terms(query),
            "ordinal": len(requirements) + 1,
        })
    return requirements


def _has_query_match(item: dict[str, Any], terms: list[str] | None = None) -> bool:
    matched = {str(term).casefold() for term in item.get("query_matched_terms") or []}
    if terms is None:
        return bool(matched) or any(str(reason).startswith("query-match:") for reason in item.get("rank_reasons") or [])
    return bool(matched.intersection(str(term).casefold() for term in terms))


def build_problem_plan(
    task: str,
    files: list[dict[str, Any]],
    graph: dict[str, Any],
    entry_points: list[str],
    *,
    per_problem_candidates: int = 3,
) -> dict[str, Any]:
    """Rank independently per problem, then merge by exact repository path.

    The returned ranked files are a scheduling order, not a filter decision. Every
    requirement remains in ``requirements`` even when no lexical candidate exists.
    """
    requirements = derive_problem_requirements(task)
    limit = max(1, int(per_problem_candidates))
    candidates_by_problem: dict[str, list[dict[str, Any]]] = {}
    ranked_by_path: dict[str, dict[str, Any]] = {}
    priority_paths: list[str] = []

    for requirement in requirements:
        ranked = rank_files(files, graph, entry_points, query=requirement.get("query") or requirement["text"])
        matched = [item for item in ranked if _has_query_match(item, requirement.get("terms") or [])]
        selected = (matched or ranked)[:limit]
        refs: list[dict[str, Any]] = []
        for position, item in enumerate(selected, start=1):
            path = str(item.get("path") or "")
            if not path:
                continue
            is_match = _has_query_match(item, requirement.get("terms") or [])
            refs.append({
                "path": path,
                "rank": position,
                "rank_score": float(item.get("rank_score") or 0.0),
                "matched": is_match,
                "rank_reasons": list(item.get("rank_reasons") or []),
            })
            current = ranked_by_path.get(path)
            if current is None:
                current = {**item, "problem_ids": [], "problem_rankings": {}}
                ranked_by_path[path] = current
            if requirement["id"] not in current["problem_ids"]:
                current["problem_ids"].append(requirement["id"])
            current["problem_rankings"][requirement["id"]] = {
                "rank": position,
                "rank_score": float(item.get("rank_score") or 0.0),
                "matched": is_match,
            }
        candidates_by_problem[requirement["id"]] = refs

    # Round-robin candidate ordering prevents one verbose problem from monopolizing
    # the HOT selection before every other problem receives a scheduling opportunity.
    for position in range(limit):
        for requirement in requirements:
            refs = candidates_by_problem.get(requirement["id"], [])
            if position < len(refs) and refs[position]["path"] not in priority_paths:
                priority_paths.append(refs[position]["path"])

    overall_ranked = rank_files(files, graph, entry_points, query=task)
    for item in overall_ranked:
        path = str(item.get("path") or "")
        if not path:
            continue
        if path not in ranked_by_path:
            ranked_by_path[path] = {**item, "problem_ids": [], "problem_rankings": {}}
        if path not in priority_paths:
            priority_paths.append(path)

    ranked_files = [ranked_by_path[path] for path in priority_paths if path in ranked_by_path]
    mandatory_paths: list[str] = []
    for requirement in requirements:
        refs = candidates_by_problem.get(requirement["id"], [])
        if refs and refs[0]["path"] not in mandatory_paths:
            mandatory_paths.append(refs[0]["path"])

    return {
        "schema": SCHEMA,
        "task": task,
        "requirements": requirements,
        "candidates_by_problem": candidates_by_problem,
        "priority_paths": priority_paths,
        "mandatory_paths": mandatory_paths,
        "ranked_files": ranked_files,
        "policy": {
            "problem_retention": "mandatory",
            "candidate_ranking_authority": "scheduling-only",
            "context_removal_authority": "exact-context-identity-only",
        },
    }


def _infer_problem_ids(item: dict[str, Any], requirements: list[dict[str, Any]]) -> list[str]:
    explicit = [str(value) for value in item.get("problem_ids") or [] if value]
    if explicit:
        rankings = item.get("problem_rankings")
        if isinstance(rankings, dict):
            return [
                problem_id
                for problem_id in explicit
                if not isinstance(rankings.get(problem_id), dict) or bool(rankings[problem_id].get("matched"))
            ]
        return explicit
    searchable = " ".join(str(item.get(key) or "") for key in ("path", "symbol", "name", "title", "content", "snippet")).casefold()
    inferred: list[str] = []
    for requirement in requirements:
        terms = [str(term).casefold() for term in requirement.get("terms") or []]
        if terms and any(term in searchable for term in terms):
            inferred.append(str(requirement["id"]))
    return inferred


def _build_batches(requirements: list[dict[str, Any]], catalog: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    catalog_by_id = {str(item["context_id"]): item for item in catalog}
    emitted: set[str] = set()
    batches: list[dict[str, Any]] = []
    current = {"problem_ids": [], "context_ids": [], "reference_context_ids": [], "estimated_tokens": 0, "overflow": False}

    def flush() -> None:
        nonlocal current
        if not current["problem_ids"]:
            return
        current["id"] = f"batch-{len(batches) + 1:03d}"
        batches.append(current)
        current = {"problem_ids": [], "context_ids": [], "reference_context_ids": [], "estimated_tokens": 0, "overflow": False}

    for requirement in requirements:
        refs = [str(value) for value in requirement.get("evidence_refs") or []]
        new_ids = [context_id for context_id in refs if context_id not in emitted]
        reference_ids = [context_id for context_id in refs if context_id in emitted]
        cost = sum(int(catalog_by_id.get(context_id, {}).get("estimated_tokens") or 0) for context_id in new_ids)
        if current["problem_ids"] and current["estimated_tokens"] + cost > budget:
            flush()
            reference_ids = [context_id for context_id in refs if context_id in emitted]
            new_ids = [context_id for context_id in refs if context_id not in emitted]
            cost = sum(int(catalog_by_id.get(context_id, {}).get("estimated_tokens") or 0) for context_id in new_ids)
        current["problem_ids"].append(requirement["id"])
        current["context_ids"].extend(context_id for context_id in new_ids if context_id not in current["context_ids"])
        current["reference_context_ids"].extend(context_id for context_id in reference_ids if context_id not in current["reference_context_ids"])
        current["estimated_tokens"] += cost
        current["overflow"] = current["overflow"] or cost > budget
        emitted.update(new_ids)
    flush()
    return batches


def finalize_problem_plan(
    plan: dict[str, Any],
    evidence: list[dict[str, Any]],
    *,
    batch_budget: int,
) -> dict[str, Any]:
    """Bind evidence once, retain all problems, and schedule overflow as batches."""
    requirements = [{**item} for item in plan.get("requirements") or [] if isinstance(item, dict)]
    requirement_ids = {str(item["id"]) for item in requirements}
    catalog_by_id: dict[str, dict[str, Any]] = {}

    for item in evidence:
        if not isinstance(item, dict) or not item.get("context_id"):
            continue
        context_id = str(item["context_id"])
        problem_ids = [value for value in _infer_problem_ids(item, requirements) if value in requirement_ids]
        current = catalog_by_id.get(context_id)
        if current is None:
            current = {
                "context_id": context_id,
                "path": item.get("path"),
                "symbol": item.get("symbol") or item.get("name"),
                "content_mode": item.get("content_mode"),
                "estimated_tokens": int(item.get("estimated_tokens") or 0),
                "used_by": [],
            }
            catalog_by_id[context_id] = current
        for problem_id in problem_ids:
            if problem_id not in current["used_by"]:
                current["used_by"].append(problem_id)

    # Unbound evidence remains in the ordinary context pack. The problem ledger
    # catalogs only evidence referenced by at least one retained problem.
    catalog = [item for item in catalog_by_id.values() if item["used_by"]]
    candidates = plan.get("candidates_by_problem") if isinstance(plan.get("candidates_by_problem"), dict) else {}
    for requirement in requirements:
        problem_id = str(requirement["id"])
        refs = [item["context_id"] for item in catalog if problem_id in item.get("used_by", [])]
        candidate_paths = [str(item.get("path")) for item in candidates.get(problem_id, []) if item.get("path")]
        matched_candidates = [item for item in candidates.get(problem_id, []) if item.get("matched")]
        requirement["evidence_refs"] = refs
        requirement["candidate_paths"] = candidate_paths
        if refs:
            requirement["status"] = "covered"
        elif matched_candidates or candidate_paths:
            requirement["status"] = "queued"
        else:
            requirement["status"] = "unresolved"

    batches = _build_batches(requirements, catalog, max(1, int(batch_budget)))
    recall_queue = [
        {
            "problem_id": item["id"],
            "query": item.get("query") or item.get("text"),
            "candidate_paths": list(item.get("candidate_paths") or []),
            "reason": "no-admitted-evidence-for-problem",
        }
        for item in requirements
        if item.get("status") != "covered"
    ]
    reference_count = sum(len(item.get("evidence_refs") or []) for item in requirements)
    covered = sum(1 for item in requirements if item.get("status") == "covered")
    return {
        "schema": SCHEMA,
        "requirements": requirements,
        "context_catalog": catalog,
        "batches": batches,
        "recall_queue": recall_queue,
        "summary": {
            "problem_count": len(requirements),
            "problems_retained": len(requirements),
            "problem_retention_rate": 1.0 if requirements else 1.0,
            "problems_covered": covered,
            "all_problems_covered": covered == len(requirements),
            "unique_context_count": len(catalog),
            "context_reference_count": reference_count,
            "duplicate_context_references_avoided": max(0, reference_count - len(catalog)),
            "batch_count": len(batches),
            "queued_problem_count": len(recall_queue),
            "budget_overflow": any(bool(batch.get("overflow")) for batch in batches),
        },
        "policy": {
            "problems_may_be_filtered": False,
            "duplicate_context_may_be_removed": True,
            "same_context_identity_emitted_once": True,
            "budget_overflow_action": "queue-next-batch-not-drop-problem",
            "contradictions_may_be_filtered": False,
        },
    }


def project_problem_context(problem_context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(problem_context, dict):
        return {
            "schema": SCHEMA,
            "requirements": [],
            "context_catalog": [],
            "batches": [],
            "recall_queue": [],
            "policy": {"problems_may_be_filtered": False},
        }
    return {
        "schema": SCHEMA,
        "requirements": [
            {
                key: item.get(key)
                for key in ("id", "text", "ordinal", "status", "evidence_refs", "candidate_paths")
                if item.get(key) is not None
            }
            for item in problem_context.get("requirements") or []
            if isinstance(item, dict)
        ],
        "context_catalog": list(problem_context.get("context_catalog") or []),
        "batches": list(problem_context.get("batches") or []),
        "recall_queue": list(problem_context.get("recall_queue") or []),
        "summary": dict(problem_context.get("summary") or {}),
        "policy": dict(problem_context.get("policy") or {}),
    }
