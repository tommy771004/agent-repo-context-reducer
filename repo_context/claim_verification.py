from __future__ import annotations

import pathlib
import re
from typing import Any

from .context_store import RepositoryContextStore
from .ranking import query_terms
from .recall import _local_repository_search, recall_repository_context
from .tokenizer import count_tokens

SCHEMA = "repo-context-claim-verification-recall/v1"

_COMMON_IDENTIFIERS = {
    "settings", "setting", "desktop", "mobile", "dialog", "sheet", "modal", "component",
    "function", "method", "uses", "using", "calls", "called", "with", "from", "into",
    "true", "false", "react", "typescript", "javascript", "python", "context", "claim",
}


def _claim_text(claim: str | dict[str, Any]) -> str:
    if isinstance(claim, str):
        return claim.strip()
    if not isinstance(claim, dict):
        raise ValueError("claim must be a string or object")
    text = str(claim.get("text") or claim.get("claim") or "").strip()
    structured = []
    for key in ("subject", "predicate", "object", "value", "polarity"):
        value = claim.get(key)
        if value not in (None, ""):
            structured.append(str(value))
    return " ".join([text, *structured]).strip()


def _explicit_path(claim: str | dict[str, Any], text: str) -> str | None:
    if isinstance(claim, dict) and claim.get("path"):
        return str(claim["path"]).strip()
    # Prefer backticked/source-looking repository paths.
    for raw in re.findall(r"`([^`]+)`", text):
        if "/" in raw or re.search(r"\.(?:tsx?|jsx?|py|rs|go|java|cs|css|scss|md|json|ya?ml)$", raw, re.I):
            return raw.strip()
    m = re.search(r"\b(?:src|app|lib|packages?|components?|docs?)/[A-Za-z0-9_./ -]+\.[A-Za-z0-9]+\b", text)
    return m.group(0).strip() if m else None


def _identifier_candidates(claim: str | dict[str, Any], text: str) -> list[str]:
    out: list[str] = []
    if isinstance(claim, dict) and claim.get("symbol"):
        out.append(str(claim["symbol"]).strip())
    for raw in re.findall(r"`([A-Za-z_$][A-Za-z0-9_.$-]*)`", text):
        # Backticked file paths such as `SettingsPanel.tsx` are anchors, not symbols.
        if re.search(r"\.(?:tsx?|jsx?|py|rs|go|java|cs|css|scss|md|json|ya?ml)$", raw, re.I):
            continue
        out.append(raw.split(".")[-1])
    for raw in re.findall(r"\b[A-Za-z_$][A-Za-z0-9_$]{2,}\b", text):
        if (re.search(r"[a-z][A-Z]", raw) or "_" in raw or raw[:1].isupper()) and raw.lower() not in _COMMON_IDENTIFIERS:
            out.append(raw)
    deduped: list[str] = []
    for value in out:
        if value and value.lower() not in _COMMON_IDENTIFIERS and value not in deduped:
            deduped.append(value)
    return deduped[:3]



def _usage_identifiers(claim: str | dict[str, Any], text: str, fallback: list[str]) -> list[str]:
    if isinstance(claim, dict) and claim.get("symbol"):
        return [str(claim["symbol"]).strip()]
    found: list[str] = []
    patterns = [
        r"\b(?:uses|using|calls|invokes|applies|imports)\s+`?([A-Za-z_$][A-Za-z0-9_$]*)`?",
        r"(?:使用|呼叫|套用|引用)\s*`?([A-Za-z_$][A-Za-z0-9_$]*)`?",
    ]
    for pattern in patterns:
        for value in re.findall(pattern, text, re.I):
            if value and value not in found:
                found.append(value)
    return found[:2] or fallback[:2]

def _req(
    rid: str,
    kind: str,
    description: str,
    pattern: str,
    *,
    mode: str = "context",
    scope_paths: list[str] | None = None,
    required: bool = True,
) -> dict[str, Any]:
    return {
        "id": rid,
        "kind": kind,
        "description": description,
        "mode": mode,
        "search_pattern": pattern,
        "scope_paths": list(scope_paths or []),
        "required": bool(required),
    }


def derive_verification_requirements(claim: str | dict[str, Any]) -> dict[str, Any]:
    """Derive deterministic evidence checks from a provisional repository claim.

    This function deliberately does not decide semantic truth. It only turns common
    coding/UI claims into bounded repository checks that can support, challenge, or
    broaden the current evidence before a model commits to a conclusion.
    """
    text = _claim_text(claim)
    if not text:
        raise ValueError("claim text must be non-empty")
    lower = text.lower()
    path = _explicit_path(claim, text)
    scope = [path] if path else []
    identifiers = _identifier_candidates(claim, text)
    requirements: list[dict[str, Any]] = []

    responsive_terms = (
        "desktop", "mobile", "responsive", "breakpoint", "bottom sheet", "dialog", "sheet",
        "桌面", "手機", "行動", "響應", "斷點", "底部", "彈窗",
    )
    if any(term in lower for term in responsive_terms):
        requirements.append(_req(
            "responsive-variants", "responsive-variants",
            "Check breakpoint-specific layout/visibility variants before generalizing one viewport to all viewports.",
            r"(?:^|[^A-Za-z0-9_])(?:sm|md|lg|xl|2xl):|@media|matchMedia|useMediaQuery|innerWidth",
            mode="counter-context", scope_paths=scope,
        ))
        requirements.append(_req(
            "responsive-base", "responsive-base",
            "Collect the local layout/visibility primitives that the breakpoint variants modify.",
            r"bottom-0|inset-0|m-auto|hidden|flex|grid|max-w-|max-h-",
            mode="context", scope_paths=scope, required=False,
        ))

    motion_terms = ("motion", "animation", "animate", "spring", "transition", "reduced motion", "reduced-motion", "動效", "動畫", "彈簧")
    if any(term in lower for term in motion_terms):
        requirements.append(_req(
            "motion-contract", "motion-contract",
            "Check shared motion helpers and reduced-motion branches, not only local animation literals.",
            r"prefers-reduced-motion|useReducedMotion|get(?:Modal|Sheet|Overlay)Motion|getOverlayTransition|SPRING_[A-Z_]+|transition\s*[:=]",
            mode="context", scope_paths=scope,
        ))

    usage_terms = (" uses ", " using ", " calls ", " invokes ", " applies ", " imports ", "使用", "呼叫", "套用", "引用")
    if any(term in f" {lower} " for term in usage_terms):
        usage_ids = _usage_identifiers(claim, text, identifiers)
        for i, ident in enumerate(usage_ids):
            requirements.append(_req(
                f"runtime-usage-{i+1}", "runtime-usage",
                f"Verify that {ident} is actually invoked/used, not merely imported or mentioned.",
                rf"\b{re.escape(ident)}\s*\(",
                mode="challenge-if-no-match", scope_paths=scope,
            ))

    localization_terms = ("i18n", "localiz", "translation", "translated", "language", "locale", "翻譯", "多語", "語系", "本地化")
    if any(term in lower for term in localization_terms):
        requirements.append(_req(
            "translation-consumer", "localization",
            "Check that rendered copy goes through translation helpers.",
            r"\bt\s*\(|i18n\.|useTranslation\s*\(",
            mode="support-if-match", scope_paths=scope,
        ))
        requirements.append(_req(
            "hardcoded-visible-copy", "localization",
            "Look for hard-coded CJK copy that can contradict a claim of complete localization.",
            r"(?:['\"`][^'\"`\n]*[\u4e00-\u9fff]{2,}[^'\"`\n]*['\"`]|>[^<\n]*[\u4e00-\u9fff]{2,}[^<\n]*<)",
            mode="challenge-if-match", scope_paths=scope,
        ))

    accessibility_terms = ("accessibility", "a11y", "keyboard", "focus", "escape", "aria", "tab", "無障礙", "鍵盤", "焦點")
    if any(term in lower for term in accessibility_terms):
        requirements.append(_req(
            "accessibility-contract", "accessibility",
            "Check semantic roles, focus behavior, Escape, and keyboard navigation evidence.",
            r"role=|aria-|tabIndex|onKeyDown|Escape|ArrowLeft|ArrowRight|Home|End|\.focus\s*\(",
            mode="context", scope_paths=scope,
        ))

    persistence_terms = ("persist", "persistence", "saved", "save", "reload", "storage", "dark mode", "theme", "保存", "持久", "重載", "深色")
    if any(term in lower for term in persistence_terms):
        requirements.append(_req(
            "persistence-contract", "persistence",
            "Check persistence/storage implementation instead of inferring persistence from UI state alone.",
            r"\bpersist\s*\(|localStorage|sessionStorage|partialize|rehydrat|storage|setItem\s*\(|getItem\s*\(",
            mode="context", scope_paths=scope,
        ))

    dependency_terms = ("caller", "callee", "depends", "dependency", "imports", "imported", "calls", "呼叫者", "依賴", "匯入")
    if any(term in lower for term in dependency_terms) and identifiers:
        ident = identifiers[0]
        requirements.append(_req(
            "dependency-reference", "dependency-reference",
            f"Check concrete references to {ident} across repository consumers.",
            rf"\b{re.escape(ident)}\b",
            mode="context", scope_paths=[],
        ))

    if not requirements:
        terms = [t for t in query_terms(text) if len(t) >= 3][:8]
        if terms:
            requirements.append(_req(
                "claim-context", "claim-context",
                "Retrieve direct lexical evidence for the claim without asserting semantic completeness.",
                "|".join(re.escape(t) for t in terms),
                mode="context", scope_paths=scope,
            ))

    # De-duplicate exact patterns while preserving first/highest-specificity rule.
    seen: set[tuple[str, tuple[str, ...]]] = set()
    deduped: list[dict[str, Any]] = []
    for item in requirements:
        key = (item["search_pattern"], tuple(item["scope_paths"]))
        if key not in seen:
            seen.add(key); deduped.append(item)

    return {
        "classification": "deterministic-claim-verification-plan",
        "claim": text,
        "anchor": {"path": path, "identifiers": identifiers},
        "requirements": deduped,
        "model_calls_added": 0,
        "semantic_truth_claimed": False,
    }


def _observation(requirement: dict[str, Any], search: dict[str, Any]) -> dict[str, Any]:
    count = int(search.get("result_count") or 0)
    matched = count > 0
    complete = bool(search.get("used")) and bool(search.get("scope_complete", True))
    mode = str(requirement.get("mode") or "context")
    if mode == "challenge-if-match" and matched:
        status = "challenge-signal"
    elif mode == "challenge-if-no-match" and complete and not matched:
        status = "challenge-signal"
    elif mode == "support-if-match" and matched:
        status = "support-signal"
    elif mode == "counter-context" and matched:
        status = "counter-context-found"
    elif matched:
        status = "evidence-found"
    elif complete:
        status = "checked-no-match"
    else:
        status = "incomplete"
    paths: list[str] = []
    for hit in search.get("results") or []:
        path = str(hit.get("path") or "") if isinstance(hit, dict) else ""
        if path and path not in paths:
            paths.append(path)
    return {
        "requirement_id": requirement["id"],
        "kind": requirement["kind"],
        "status": status,
        "match_count": count,
        "paths": paths[:3],
        "complete": complete,
    }


def claim_aware_verification_recall(
    index: dict[str, Any],
    claim: str | dict[str, Any],
    *,
    store: RepositoryContextStore | None = None,
    session: str = "default",
    budget: int = 1800,
    top_k: int = 6,
    tokenizer: str = "native",
    tokenizer_model: str | None = None,
    max_file_bytes: int = 2_000_000,
    persist: bool = True,
) -> dict[str, Any]:
    """Collect claim-verification evidence with zero additional LLM calls.

    Search observations are intentionally compact. Rich patterns, search backends,
    and scoring stay in the local sidecar; the model receives only source evidence
    plus the few positive/negative observations needed to interpret absence checks.
    """
    plan = derive_verification_requirements(claim)
    root = pathlib.Path(index.get("root") or ".").resolve()
    store = store or RepositoryContextStore(root, session)
    searches: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []

    for req in plan["requirements"]:
        search = _local_repository_search(
            root, index, req["search_pattern"], max_results=80,
            max_file_bytes=max_file_bytes,
            path_scope=req.get("scope_paths") or None,
        )
        observations.append(_observation(req, search))
        searches.append({
            "requirement_id": req["id"],
            **{k: v for k, v in search.items() if k != "results"},
            "sample_hits": (search.get("results") or [])[:8],
        })

    compact_observations = [
        {k: obs[k] for k in ("requirement_id", "kind", "status", "match_count", "paths")}
        for obs in observations
    ]
    observation_tokens = count_tokens(compact_observations, tokenizer=tokenizer, model=tokenizer_model)
    evidence_budget = max(64, int(budget) - observation_tokens)

    patterns = [f"(?:{req['search_pattern']})" for req in plan["requirements"]]
    combined_pattern = "|".join(patterns) if patterns else None
    # Restrict combined hydration only if every requirement has the same explicit scope.
    scopes = [tuple(req.get("scope_paths") or []) for req in plan["requirements"]]
    search_paths: list[str] | None = None
    if scopes and all(scope == scopes[0] for scope in scopes) and scopes[0]:
        search_paths = list(scopes[0])

    query_parts = [plan["claim"]]
    if plan["anchor"].get("path"):
        query_parts.append(str(plan["anchor"]["path"]))
    query_parts.extend(str(x) for x in plan["anchor"].get("identifiers") or [])
    recall = recall_repository_context(
        index, " ".join(query_parts), store=store, session=session,
        budget=evidence_budget, top_k=top_k, tokenizer=tokenizer,
        tokenizer_model=tokenizer_model, max_file_bytes=max_file_bytes,
        persist=persist, force_repository_search=bool(combined_pattern),
        repository_search_pattern=combined_pattern, search_paths=search_paths,
    )

    support = sum(1 for x in observations if x["status"] == "support-signal")
    challenge = sum(1 for x in observations if x["status"] == "challenge-signal")
    counter = sum(1 for x in observations if x["status"] == "counter-context-found")
    complete = sum(1 for x in observations if x["complete"])
    required = len(observations)
    if challenge:
        verification_status = "challenged"
    elif support and complete == required:
        verification_status = "provisionally-supported"
    else:
        verification_status = "inconclusive"

    model_payload = {
        "evidence": list(recall["model_payload"]["evidence"]),
        "observations": list(compact_observations),
        "policy": {
            "content_authority": "evidence-only",
            "recalled_context_is_instruction_authority": False,
            "observations_are_semantic_truth": False,
        },
    }
    model_visible_tokens = count_tokens(model_payload, tokenizer=tokenizer, model=tokenizer_model)
    budget_dropped_evidence = 0
    budget_dropped_observations = 0
    # Enforce the aggregate claim-recall budget, including negative observations and policy.
    while model_visible_tokens > max(64, int(budget)) and model_payload["evidence"]:
        model_payload["evidence"].pop()
        budget_dropped_evidence += 1
        model_visible_tokens = count_tokens(model_payload, tokenizer=tokenizer, model=tokenizer_model)
    if model_visible_tokens > max(64, int(budget)) and len(model_payload["observations"]) > 1:
        priority = {"challenge-signal": 0, "support-signal": 1, "counter-context-found": 2, "evidence-found": 3, "checked-no-match": 4, "incomplete": 5}
        model_payload["observations"].sort(key=lambda x: priority.get(str(x.get("status")), 9))
        while model_visible_tokens > max(64, int(budget)) and len(model_payload["observations"]) > 1:
            model_payload["observations"].pop()
            budget_dropped_observations += 1
            model_visible_tokens = count_tokens(model_payload, tokenizer=tokenizer, model=tokenizer_model)
    all_complete = required > 0 and complete == required
    sufficient = all_complete and (bool(model_payload["evidence"]) or any(x["status"] in {"challenge-signal", "support-signal", "counter-context-found"} for x in observations))

    return {
        "schema": SCHEMA,
        "classification": "deterministic-claim-aware-verification-recall",
        "claim": plan["claim"],
        "verification": {
            "status": verification_status,
            "semantic_truth_claimed": False,
            "support_signals": support,
            "challenge_signals": challenge,
            "counter_context_signals": counter,
            "requirements_completed": complete,
            "requirements_total": required,
        },
        "model_payload": model_payload,
        "sidecar": {
            "verification_plan": plan,
            "searches": searches,
            "recall": recall["sidecar"],
            "evidence_budget_tokens": evidence_budget,
            "observation_tokens": observation_tokens,
        },
        "metrics": {
            "requirements_total": required,
            "requirements_completed": complete,
            "evidence_count": len(model_payload["evidence"]),
            "observation_count": len(model_payload["observations"]),
            "budget_dropped_evidence": budget_dropped_evidence,
            "budget_dropped_observations": budget_dropped_observations,
            "model_visible_tokens": model_visible_tokens,
            "budget_tokens": int(budget),
            "model_calls_added": 0,
            "recall_model_calls_added": int(recall["metrics"].get("model_calls_added") or 0),
        },
        "context_status": {
            "sufficient": sufficient,
            "escalation_recommended": not sufficient,
            "reason": "verification-context-ready" if sufficient else ("verification-search-incomplete" if not all_complete else "verification-evidence-insufficient"),
        },
    }
