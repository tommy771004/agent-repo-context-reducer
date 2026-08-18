from __future__ import annotations

from typing import Any

from .tokenizer import count_tokens

SCHEMA = "repo-context-model-context/v1"
SIDECAR_SCHEMA = "repo-context-model-context-sidecar/v1"


def _pick(item: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: item[key] for key in keys if key in item and item[key] is not None}


def split_model_context(
    context_pack: dict[str, Any] | None,
    *,
    tokenizer: str = "native",
    tokenizer_model: str | None = None,
) -> dict[str, Any]:
    if not isinstance(context_pack, dict):
        return {
            "model_payload": None,
            "sidecar": None,
            "metrics": {"rich_context_tokens": 0, "model_context_tokens": 0, "model_visible_tokens_avoided": 0, "model_visible_reduction_ratio": 0.0},
        }

    files: list[dict[str, Any]] = []
    file_meta: list[dict[str, Any]] = []
    for index, item in enumerate(context_pack.get("files") or []):
        if not isinstance(item, dict):
            continue
        files.append(_pick(item, (
            "path", "language", "lines", "imports", "classes", "types", "functions",
            "exports", "routes", "content", "content_mode",
        )))
        file_meta.append({
            "index": index,
            **_pick(item, ("context_id", "provenance", "trust", "voi", "rank_score", "rank_reasons", "selection_score", "fingerprint", "estimated_tokens", "structure_dedup")),
        })

    symbols: list[dict[str, Any]] = []
    symbol_meta: list[dict[str, Any]] = []
    for index, item in enumerate(context_pack.get("symbols") or []):
        if not isinstance(item, dict):
            continue
        symbols.append(_pick(item, (
            "path", "name", "kind", "signature", "start_line", "end_line", "content", "content_mode",
        )))
        symbol_meta.append({
            "index": index,
            **_pick(item, ("context_id", "provenance", "trust", "voi", "selection_score", "fingerprint", "estimated_tokens", "already_seen")),
        })

    external: list[dict[str, Any]] = []
    external_meta: list[dict[str, Any]] = []
    for index, item in enumerate(context_pack.get("external_context") or []):
        if not isinstance(item, dict):
            continue
        external.append(_pick(item, ("provider", "path", "url", "title", "content", "snippet", "content_mode")))
        external_meta.append({
            "index": index,
            **_pick(item, ("fingerprint", "provenance", "trust", "support", "estimated_tokens", "context_id")),
        })

    model_payload = {
        "schema": SCHEMA,
        "files": files,
        "symbols": symbols,
        "external_context": external,
        "policy": {"content_authority": "evidence-only"},
    }
    sidecar = {
        "schema": SIDECAR_SCHEMA,
        "repository_provenance": context_pack.get("repository_provenance"),
        "trust_summary": context_pack.get("trust_summary"),
        "coverage": context_pack.get("coverage"),
        "budget": context_pack.get("budget"),
        "notes": context_pack.get("notes"),
        "strategy": context_pack.get("strategy"),
        "context_store": context_pack.get("context_store"),
        "recall_policy": context_pack.get("recall_policy"),
        "file_metadata": file_meta,
        "symbol_metadata": symbol_meta,
        "external_metadata": external_meta,
    }
    rich_tokens = count_tokens(context_pack, tokenizer=tokenizer, model=tokenizer_model)
    model_tokens = count_tokens(model_payload, tokenizer=tokenizer, model=tokenizer_model)
    return {
        "model_payload": model_payload,
        "sidecar": sidecar,
        "metrics": {
            "rich_context_tokens": rich_tokens,
            "model_context_tokens": model_tokens,
            "sidecar_tokens": count_tokens(sidecar, tokenizer=tokenizer, model=tokenizer_model),
            "model_visible_tokens_avoided": max(0, rich_tokens - model_tokens),
            "model_visible_reduction_ratio": round(1 - model_tokens / max(1, rich_tokens), 4),
            "control_plane_serialized_to_model": False,
        },
    }


def project_verification_context(
    context_pack: dict[str, Any] | None,
    model_packet: dict[str, Any] | None,
    *,
    max_tokens: int,
    tokenizer: str = "native",
    tokenizer_model: str | None = None,
) -> dict[str, Any]:
    """Project only repository evidence referenced by a model synthesis packet.

    Graders need enough source material to verify claims, but re-sending the full lane
    context duplicates evidence already present in the synthesis packet. This projection
    admits only files/symbols/external blocks whose path/URL is referenced by packet
    sources, and keeps the same evidence-only trust boundary.
    """
    thin = split_model_context(context_pack, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
    model = thin.get("model_payload") if isinstance(thin, dict) else None
    sources = model_packet.get("sources") if isinstance(model_packet, dict) and isinstance(model_packet.get("sources"), dict) else {}
    identities: set[str] = set()
    for source in sources.values():
        if isinstance(source, str) and source:
            identities.add(source)
        elif isinstance(source, dict):
            for key in ("path", "url"):
                value = source.get(key)
                if isinstance(value, str) and value:
                    identities.add(value)

    out: dict[str, Any] = {
        "schema": SCHEMA,
        "files": [],
        "symbols": [],
        "external_context": [],
        "policy": {
            "content_authority": "evidence-only",
            "projection": "source-targeted-verification",
        },
    }
    target = max(0, int(max_tokens))
    used = count_tokens(out, tokenizer=tokenizer, model=tokenizer_model)
    admitted = 0
    dropped_for_budget = 0

    def matches(item: dict[str, Any]) -> bool:
        return any(isinstance(item.get(key), str) and item.get(key) in identities for key in ("path", "url"))

    if isinstance(model, dict) and identities:
        # Symbols are the most precise source representation, then files, then external blocks.
        for key in ("symbols", "files", "external_context"):
            for item in model.get(key) or []:
                if not isinstance(item, dict) or not matches(item):
                    continue
                cost = count_tokens(item, tokenizer=tokenizer, model=tokenizer_model)
                if target > 0 and used + cost <= target:
                    out[key].append(item)
                    used += cost
                    admitted += 1
                else:
                    dropped_for_budget += 1
    return {
        "model_payload": out,
        "metrics": {
            "referenced_source_count": len(identities),
            "admitted_blocks": admitted,
            "dropped_for_budget": dropped_for_budget,
            "model_context_tokens": used,
            "target_tokens": target,
            "full_model_context_tokens": int((thin.get("metrics") or {}).get("model_context_tokens", 0)),
            "projection": "source-targeted-verification",
        },
    }
