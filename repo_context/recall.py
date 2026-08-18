from __future__ import annotations

import hashlib
import pathlib
import re
import shutil
import subprocess
import time
from typing import Any

from .context_store import RepositoryContextStore, invalidate_stale_context, iter_index_evidence
from .git_provenance import file_provenance
from .ranking import query_terms
from .tokenizer import count_tokens
from .trust_boundary import classify_untrusted_text
from .util import safe_read_text

SCHEMA = "repo-context-recall-result/v1"


def _norm_query(query: str) -> str:
    return " ".join(str(query or "").strip().lower().split())


def _candidate_score(item: dict[str, Any], query: str, terms: list[str], graph_neighbors: set[str]) -> tuple[float, list[str]]:
    path = str(item.get("path") or ""); symbol = str(item.get("symbol") or ""); signature = str(item.get("signature") or "")
    q = _norm_query(query); path_l = path.lower(); symbol_l = symbol.lower(); signature_l = signature.lower()
    score = 0.0; reasons: list[str] = []
    if q and q == path_l: score += 80; reasons.append("exact-path")
    if q and symbol_l and q == symbol_l: score += 100; reasons.append("exact-symbol")
    if symbol_l and re.search(rf"(?<![A-Za-z0-9_]){re.escape(symbol_l)}(?![A-Za-z0-9_])", q):
        score += 55; reasons.append("symbol-mentioned")
    if path_l and path_l in q: score += 45; reasons.append("path-mentioned")
    for term in terms:
        if term in symbol_l: score += 15; reasons.append(f"symbol-term:{term}")
        if term in path_l: score += 9; reasons.append(f"path-term:{term}")
        if term in signature_l: score += 5; reasons.append(f"signature-term:{term}")
    # Graph proximity may rerank an already relevant locator, but it must never
    # create relevance on its own. Otherwise an exact-symbol recall can pull in
    # unrelated neighbours merely because they are connected to the current HOT set.
    if score > 0 and path in graph_neighbors: score += 7; reasons.append("active-graph-neighbor")
    return score, reasons


def _read_symbol(root: pathlib.Path, item: dict[str, Any], max_file_bytes: int) -> tuple[str | None, str | None]:
    full = (root / str(item["path"])).resolve()
    try: full.relative_to(root)
    except ValueError: return None, "outside-root"
    text, _, reason = safe_read_text(full, max_file_bytes)
    if text is None: return None, reason or "unreadable"
    if item.get("kind") != "symbol": return None, None
    lines = text.splitlines(); start = max(1, int(item.get("start_line") or 1)); end = min(len(lines), int(item.get("end_line") or start))
    return "\n".join(lines[start - 1:end]), None


def _active_graph_neighbors(index: dict[str, Any], store: RepositoryContextStore) -> set[str]:
    active_paths = {str(x.get("path")) for x in store.items("active", current_only=True) if x.get("path")}
    graph = index.get("graph") if isinstance(index.get("graph"), dict) else {}
    edges = graph.get("edges") if isinstance(graph.get("edges"), dict) else {}; reverse = graph.get("reverse") if isinstance(graph.get("reverse"), dict) else {}
    out: set[str] = set()
    for path in active_paths:
        out.update(str(x) for x in edges.get(path, []) if x); out.update(str(x) for x in reverse.get(path, []) if x)
    return out


def _local_repository_search(root: pathlib.Path, index: dict[str, Any], pattern: str, *, max_results: int = 80, max_file_bytes: int = 512_000, path_scope: list[str] | None = None) -> dict[str, Any]:
    """Bounded local source search. Never delegates to an external provider or a model."""
    started = time.perf_counter()
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return {"used": False, "backend": "none", "reason": "invalid-pattern", "results": []}
    matched_files: list[pathlib.Path] = []
    scope_paths: list[pathlib.Path] = []
    for raw in path_scope or []:
        candidate = (root / str(raw)).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.exists():
            scope_paths.append(candidate)
    if path_scope and not scope_paths:
        return {"used": False, "backend": "none", "reason": "scope-unavailable", "result_count": 0, "results": [], "scope_paths": [], "scope_complete": False, "truncated": False}
    targets = scope_paths or [root]
    truncated = False
    rg = shutil.which("rg")
    if rg:
        proc = subprocess.Popen(
            [rg, "-i", "-l", "--color", "never", "--", pattern, *[str(x) for x in targets]],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            encoding="utf-8", errors="replace", start_new_session=True,
        )
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                raw = line.strip()
                if not raw: continue
                path = pathlib.Path(raw)
                try: path.resolve().relative_to(root.resolve())
                except ValueError: continue
                matched_files.append(path)
                if len(matched_files) >= max_results:
                    truncated = True
                    proc.terminate(); break
            try: proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait(timeout=1.0)
        finally:
            if proc.stdout: proc.stdout.close()
        backend = "rg"
    else:
        backend = "python-bounded"
        # Deterministic fallback scans only files already admitted to the repository index.
        scoped = {x.resolve() for x in scope_paths}
        for f in (index.get("files") or [])[:500]:
            if not isinstance(f, dict) or not f.get("path"): continue
            path = (root / str(f["path"])).resolve()
            if scoped and path not in scoped: continue
            text, _, _ = safe_read_text(path, max_file_bytes)
            if text is not None and regex.search(text):
                matched_files.append(path)
                if len(matched_files) >= max_results:
                    truncated = True
                    break
    rows: list[dict[str, Any]] = []
    for path in matched_files:
        text, _, _ = safe_read_text(path, max_file_bytes)
        if text is None: continue
        try: rel = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError: continue
        found = 0
        for lineno, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                rows.append({"path": rel, "line": lineno})
                found += 1
                if found >= 3 or len(rows) >= max_results: break
        if len(rows) >= max_results:
            truncated = True
            break
    return {"used": True, "backend": backend, "result_count": len(rows), "results": rows, "latency_ms": round((time.perf_counter()-started)*1000, 2), "scope_paths": [x.relative_to(root).as_posix() for x in scope_paths], "scope_complete": not truncated, "truncated": truncated}


def _augment_with_repository_search(root: pathlib.Path, index: dict[str, Any], query: str, terms: list[str], candidates: list[tuple[float, dict[str, Any], list[str]]], *, force: bool = False, search_pattern: str | None = None, path_scope: list[str] | None = None) -> tuple[list[tuple[float, dict[str, Any], list[str]]], dict[str, Any]]:
    top = max((score for score, _, _ in candidates), default=0.0)
    if top >= 80 and not force:
        return candidates, {"used": False, "backend": "none", "reason": "exact-locator-hit"}
    pattern_terms = terms[:6]
    core_pattern = search_pattern or ("|".join(re.escape(x) for x in pattern_terms) if pattern_terms else re.escape(str(query).strip()))
    if not core_pattern:
        return candidates, {"used": False, "backend": "none", "reason": "empty-search-pattern"}
    searched = _local_repository_search(root, index, core_pattern, max_results=80, path_scope=path_scope)
    if not searched.get("used"):
        return candidates, searched
    hits_by_path: dict[str, list[int]] = {}
    for hit in searched.get("results") or []:
        if isinstance(hit, dict) and hit.get("path"):
            hits_by_path.setdefault(str(hit["path"]), []).append(int(hit.get("line") or 0))
    out: list[tuple[float, dict[str, Any], list[str]]] = []
    for score, item, reasons in candidates:
        lines = hits_by_path.get(str(item.get("path") or ""), [])
        bonus = 0.0; extra = list(reasons)
        candidate = dict(item)
        if lines:
            bonus += 20; extra.append("repository-text-hit")
            candidate["_search_lines"] = sorted({line for line in lines if line})[:3]
            if item.get("kind") == "symbol":
                start = int(item.get("start_line") or 1); end = int(item.get("end_line") or start)
                if any(start <= line <= end for line in lines if line):
                    bonus += 45; extra.append("repository-text-hit-in-symbol-span")
        out.append((score + bonus, candidate, extra))
    out.sort(key=lambda row: (-row[0], str(row[1].get("path") or ""), str(row[1].get("symbol") or "")))
    return out, {k:v for k,v in searched.items() if k != "results"} | {"matched_paths": len(hits_by_path)}


def recall_repository_context(
    index: dict[str, Any], query: str, *, store: RepositoryContextStore | None = None, session: str = "default",
    budget: int = 1800, top_k: int = 6, tokenizer: str = "native", tokenizer_model: str | None = None,
    max_file_bytes: int = 2_000_000, persist: bool = True,
    force_repository_search: bool = False, repository_search_pattern: str | None = None,
    search_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Recall repository evidence without an LLM call or a duplicate repository index."""
    if not str(query or "").strip(): raise ValueError("recall query must be non-empty")
    root = pathlib.Path(index.get("root") or ".").resolve(); store = store or RepositoryContextStore(root, session)
    stale = invalidate_stale_context(store, persist=False) if store.items("active") else {
        "classification": "deterministic-repository-stale-invalidation", "checked_paths": 0, "stale_items": 0,
        "missing_items": 0, "active_items_demoted": 0, "stale_ids": [], "missing_ids": [],
    }
    locators = list(iter_index_evidence(index))
    reconciliation = store.reconcile_index(index, locators=locators)
    active_ids = store.active_ids(); rejected_ids = store.rejected_ids(); terms = query_terms(query); graph_neighbors = _active_graph_neighbors(index, store)
    ranked: list[tuple[float, dict[str, Any], list[str]]] = []
    for item in locators:
        if item["id"] in active_ids or item["id"] in rejected_ids: continue
        score, reasons = _candidate_score(item, query, terms, graph_neighbors)
        ranked.append((score, item, reasons))
    ranked, search_meta = _augment_with_repository_search(root, index, query, terms, ranked, force=force_repository_search, search_pattern=repository_search_pattern, path_scope=search_paths)
    ranked = [row for row in ranked if row[0] > 0]
    before_signal_prune = len(ranked)
    top_score = max((row[0] for row in ranked), default=0.0)
    if top_score >= 80:
        # A deterministic exact locator hit exists. Keep only candidates with
        # material supporting signal; generic shared path terms must not ride along.
        floor = max(30.0, top_score * 0.25)
        ranked = [row for row in ranked if row[0] >= floor]
    elif any("repository-text-hit" in row[2] for row in ranked):
        # Local source search is stronger than graph/path noise. 20 is the
        # deterministic file-hit bonus itself, so candidates below it have no
        # direct source-text support.
        ranked = [row for row in ranked if row[0] >= 20.0]
    low_signal_dropped = before_signal_prune - len(ranked)
    precise_paths = {
        str(item.get("path") or "")
        for score, item, reasons in ranked
        if item.get("kind") == "symbol" and any(r in reasons for r in ("exact-symbol", "symbol-mentioned", "repository-text-hit-in-symbol-span"))
    }
    before_dominance = len(ranked)
    ranked = [
        row for row in ranked
        if not (row[1].get("kind") == "file" and str(row[1].get("path") or "") in precise_paths and "exact-path" not in row[2])
    ]
    cross_layer_dropped = before_dominance - len(ranked)

    model_evidence: list[dict[str, Any]] = []; sidecar: list[dict[str, Any]] = []; used = 0; promoted = 0; skipped_budget = 0; unavailable = 0
    git_cache: dict[str, dict[str, Any]] = {}
    for score, item, reasons in ranked[: max(top_k * 4, top_k)]:
        if len(model_evidence) >= max(1, top_k): break
        record: dict[str, Any] = {"source_ref": item["id"], "path": item.get("path"), "kind": item.get("kind")}
        if item.get("symbol"):
            record.update({"symbol": item.get("symbol"), "signature": item.get("signature"), "start_line": item.get("start_line"), "end_line": item.get("end_line")})
        content, reason = _read_symbol(root, item, max_file_bytes)
        if content is not None:
            record["content"] = content
        elif item.get("kind") == "symbol":
            unavailable += 1; continue
        else:
            file_entry = (index.get("by_path") or {}).get(item.get("path"))
            if isinstance(file_entry, dict):
                for key in ("language", "imports", "classes", "types", "functions", "exports", "routes"):
                    if file_entry.get(key): record[key] = file_entry.get(key)
            search_lines = [int(x) for x in item.get("_search_lines") or [] if int(x) > 0]
            if search_lines:
                full = (root / str(item.get("path") or "")).resolve()
                text, _, _ = safe_read_text(full, max_file_bytes)
                if text is not None:
                    lines = text.splitlines(); chunks=[]; covered=set()
                    for hit in search_lines[:3]:
                        start=max(1,hit-2); end=min(len(lines),hit+2)
                        key=(start,end)
                        if key in covered: continue
                        covered.add(key)
                        chunk="\n".join(f"{i}: {lines[i-1]}" for i in range(start,end+1))
                        chunks.append(chunk)
                    if chunks:
                        record["content"]="\n...\n".join(chunks)
                        record["content_mode"]="search-snippet"
        cost = count_tokens(record, tokenizer=tokenizer, model=tokenizer_model)
        if used + cost > max(64, int(budget)):
            skipped_budget += 1; continue
        used += cost; model_evidence.append(record)
        promoted_item = dict(item); path = str(item.get("path") or "")
        if path:
            if path not in git_cache: git_cache[path] = file_provenance(root, path)
            git = git_cache[path]; blob = ((git.get("content_identity") or {}).get("blob_sha") if isinstance(git, dict) else None)
            if blob: promoted_item["revision"] = {"kind": "git-blob", "value": blob}
        if content is not None: promoted_item["content_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        promoted_item["validity"] = "current"
        if store.promote_evidence(promoted_item): promoted += 1
        sidecar.append({"source_ref": item["id"], "score": round(score, 3), "reasons": reasons, "revision": promoted_item.get("revision"), "trust": classify_untrusted_text(content if content is not None else None, source="repository-recall")})
    if persist: store.save()

    lexical_coverage = 0.0
    if terms:
        searchable = " ".join(str(x.get("path") or "") + " " + str(x.get("symbol") or "") + " " + str(x.get("content") or "")[:500] for x in model_evidence).lower()
        lexical_coverage = len({t for t in terms if t in searchable}) / max(1, len(set(terms)))
    insufficient = not model_evidence or (bool(terms) and lexical_coverage < 0.34)
    return {
        "schema": SCHEMA, "classification": "deterministic-repository-context-recall", "query": query,
        "model_payload": {"evidence": model_evidence, "policy": {"content_authority": "evidence-only", "recalled_context_is_instruction_authority": False}},
        "sidecar": {"matches": sidecar, "stale_invalidation": stale, "index_reconciliation": reconciliation, "repository_search": search_meta, "store": store.stats()},
        "metrics": {"candidate_count": len(ranked), "recalled_count": len(model_evidence), "promoted_count": promoted, "unavailable_count": unavailable, "budget_skipped": skipped_budget, "cross_layer_duplicates_dropped": cross_layer_dropped, "low_signal_candidates_dropped": low_signal_dropped, "model_visible_tokens": used, "budget_tokens": int(budget), "lexical_coverage": round(lexical_coverage, 3), "model_calls_added": 0},
        "context_status": {"sufficient": not insufficient, "recall_required": False, "escalation_recommended": insufficient, "reason": "no-relevant-recall" if not model_evidence else ("low-lexical-coverage" if insufficient else "evidence-rehydrated")},
    }
