from __future__ import annotations

from typing import Any

from .filter_engine import stable_fingerprint
from .tokenizer import count_tokens

MODEL_PACKET_SCHEMA = "repo-context-model-packet/v1"
MODEL_PACKET_SIDECAR_SCHEMA = "repo-context-model-packet-sidecar/v1"


def _compact_source(source: Any) -> Any:
    if isinstance(source, str):
        return source
    if not isinstance(source, dict):
        return str(source) if source is not None else None
    out: dict[str, Any] = {}
    for key in ("path", "symbol", "lines", "line", "url", "provider"):
        value = source.get(key)
        if value is not None and value != "" and value != []:
            out[key] = value
    return out or source


def _model_finding(item: dict[str, Any], source_ref: str | None) -> dict[str, Any]:
    reducer = item.get("reducer") if isinstance(item.get("reducer"), dict) else {}
    out: dict[str, Any] = {
        "claim": item.get("claim"),
        "evidence": item.get("evidence"),
    }
    if source_ref:
        out["source_ref"] = source_ref
    if item.get("confidence") is not None:
        out["confidence"] = item.get("confidence")
    agreement = int(reducer.get("agreement_count", 1) or 1)
    if agreement > 1:
        out["agreement"] = agreement
    independent = int(reducer.get("independent_evidence_count", 0) or 0)
    if independent > 1:
        out["independent_evidence"] = independent
    for key in ("value", "polarity", "unit", "period"):
        if key in item:
            out[key] = item[key]
    return {k: v for k, v in out.items() if v is not None}


def split_model_packet(
    synthesis_packet: dict[str, Any],
    *,
    tokenizer: str = "native",
    tokenizer_model: str | None = None,
) -> dict[str, Any]:
    """Split rich reducer state from the model-visible evidence packet.

    The model payload contains only evidence needed for synthesis plus one packet-level
    trust boundary. Provenance, reducer internals, candidate analysis, audit details and
    telemetry remain in the sidecar and are never required to be sent to a model.
    """
    source_ids: dict[str, str] = {}
    compact_sources: dict[str, Any] = {}
    rich_sources: dict[str, Any] = {}
    finding_sidecar: list[dict[str, Any]] = []

    def source_ref(source: Any) -> str | None:
        if source is None or source == "":
            return None
        fp = stable_fingerprint(source)
        if fp not in source_ids:
            ref = f"S{len(source_ids) + 1}"
            source_ids[fp] = ref
            compact_sources[ref] = _compact_source(source)
            rich_sources[ref] = source
        return source_ids[fp]

    model_findings: list[dict[str, Any]] = []
    for index, item in enumerate(synthesis_packet.get("findings") or []):
        if not isinstance(item, dict):
            continue
        ref = source_ref(item.get("source"))
        model_findings.append(_model_finding(item, ref))
        finding_sidecar.append({
            "section": "finding",
            "index": index,
            "source_ref": ref,
            "reducer": item.get("reducer"),
            "canonicalKey": item.get("canonicalKey"),
        })

    model_contradictions: list[dict[str, Any]] = []
    for c_index, contradiction in enumerate(synthesis_packet.get("contradictions") or []):
        if not isinstance(contradiction, dict):
            continue
        claims: list[dict[str, Any]] = []
        for s_index, side in enumerate(contradiction.get("claims") or []):
            if not isinstance(side, dict):
                continue
            ref = source_ref(side.get("source"))
            claims.append(_model_finding(side, ref))
            finding_sidecar.append({
                "section": "contradiction",
                "index": c_index,
                "side_index": s_index,
                "source_ref": ref,
                "reducer": side.get("reducer"),
                "canonicalKey": side.get("canonicalKey"),
            })
        model_contradictions.append({
            "key": contradiction.get("key"),
            "reasons": list(contradiction.get("reasons") or []),
            "claims": claims,
        })

    audit = synthesis_packet.get("filter_audit") if isinstance(synthesis_packet.get("filter_audit"), dict) else None
    model_payload: dict[str, Any] = {
        "schema": MODEL_PACKET_SCHEMA,
        "findings": model_findings,
        "contradictions": model_contradictions,
        "sources": compact_sources,
        "policy": {
            "content_authority": "evidence-only",
            "contradictions_preserved": True,
        },
    }
    # A single boolean gate is useful to downstream graders. Full violations/warnings stay
    # in the sidecar and must not be serialized into every model call.
    if audit is not None:
        model_payload["filter_audit"] = {"passed": bool(audit.get("passed"))}

    sidecar = {
        "schema": MODEL_PACKET_SIDECAR_SCHEMA,
        "sources": rich_sources,
        "finding_metadata": finding_sidecar,
        "reducer_summary": synthesis_packet.get("reducer_summary"),
        "trust_summary": synthesis_packet.get("trust_summary"),
        "policy": synthesis_packet.get("policy"),
        "filter_audit": audit,
        "budget": synthesis_packet.get("budget"),
    }

    rich_tokens = count_tokens(synthesis_packet, tokenizer=tokenizer, model=tokenizer_model)
    model_tokens = count_tokens(model_payload, tokenizer=tokenizer, model=tokenizer_model)
    sidecar_tokens = count_tokens(sidecar, tokenizer=tokenizer, model=tokenizer_model)
    return {
        "model_payload": model_payload,
        "sidecar": sidecar,
        "metrics": {
            "rich_packet_tokens": rich_tokens,
            "model_payload_tokens": model_tokens,
            "sidecar_tokens": sidecar_tokens,
            "model_visible_tokens_avoided": max(0, rich_tokens - model_tokens),
            "model_visible_reduction_ratio": round(1 - model_tokens / max(1, rich_tokens), 4),
            "control_plane_serialized_to_model": False,
        },
    }
