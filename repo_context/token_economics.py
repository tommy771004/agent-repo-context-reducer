from __future__ import annotations

from typing import Any

from .tokenizer import count_tokens

SCHEMA = "repo-context-token-economics/v1"


def request_token_breakdown(request: dict[str, Any], *, tokenizer: str = "native", tokenizer_model: str | None = None) -> dict[str, int]:
    """Estimate evidence/data-plane versus orchestration/control-plane input tokens.

    Only model-relevant evidence fields are counted as data-plane. Schema tags, policy,
    audit booleans, status-only dependency records and runtime framing remain control-plane.
    The split is deterministic and clamped to the total serialized request token count.
    """
    total = count_tokens(request, tokenizer=tokenizer, model=tokenizer_model)

    context = request.get("context") if request.get("context") is not None else request.get("context_pack")
    context_evidence = None
    if isinstance(context, dict):
        context_evidence = {
            key: context.get(key)
            for key in ("files", "symbols", "external_context")
            if context.get(key)
        }

    synthesis = request.get("synthesis_packet")
    synthesis_evidence = None
    if isinstance(synthesis, dict):
        synthesis_evidence = {
            key: synthesis.get(key)
            for key in ("findings", "contradictions", "sources")
            if synthesis.get(key)
        }

    handoffs = request.get("dependency_handoffs")
    handoff_evidence = None
    if isinstance(handoffs, dict) and handoffs:
        status_only_keys = {"status", "handoff_available", "role"}
        is_status_only = all(
            isinstance(value, dict) and set(value).issubset(status_only_keys)
            for value in handoffs.values()
        )
        if not is_status_only:
            handoff_evidence = handoffs

    raw_data = sum(
        count_tokens(value, tokenizer=tokenizer, model=tokenizer_model)
        for value in (context_evidence, synthesis_evidence, handoff_evidence)
        if value
    )
    data = min(total, raw_data)
    return {
        "total_input_tokens_estimated": total,
        "data_plane_tokens_estimated": data,
        "control_plane_tokens_estimated": max(0, total - data),
    }


def summarize_token_economics(
    *,
    aggregate_input_tokens: int,
    aggregate_output_tokens: int,
    baseline_input_tokens: int,
    baseline_output_tokens: int = 0,
    data_plane_input_tokens: int | None = None,
    control_plane_input_tokens: int | None = None,
    baseline_classification: str = "estimated-single-call-direct-baseline",
    baseline_tokens_source: str = "estimated",
    pipeline_input_tokens_source: str = "estimated",
    pipeline_output_tokens_source: str = "estimated",
    tokenizer: str | None = None,
    tokenizer_exact: bool | None = None,
) -> dict[str, Any]:
    aggregate_input = max(0, int(aggregate_input_tokens))
    aggregate_output = max(0, int(aggregate_output_tokens))
    baseline_input = max(0, int(baseline_input_tokens))
    baseline_output = max(0, int(baseline_output_tokens))
    total = aggregate_input + aggregate_output
    baseline_total = baseline_input + baseline_output
    net = baseline_total - total
    sources = {str(baseline_tokens_source), str(pipeline_input_tokens_source), str(pipeline_output_tokens_source)}
    if sources == {"estimated"}:
        comparison_quality = "comparable-estimates"
        interpretation = "Comparable estimator-based token economics; still not a provider billing statement."
    elif sources == {"provider-reported"}:
        comparison_quality = "provider-reported"
        interpretation = "Comparable provider-reported token economics."
    else:
        comparison_quality = "mixed-measurement"
        interpretation = "Directional only: provider-reported and estimated token counts are mixed in this comparison."
    return {
        "schema": SCHEMA,
        "baseline": {
            "classification": baseline_classification,
            "input_tokens": baseline_input,
            "output_tokens": baseline_output,
            "total_tokens": baseline_total,
        },
        "observed_or_estimated_pipeline": {
            "aggregate_model_input_tokens": aggregate_input,
            "aggregate_model_output_tokens": aggregate_output,
            "total_model_tokens": total,
            "data_plane_input_tokens": None if data_plane_input_tokens is None else max(0, int(data_plane_input_tokens)),
            "control_plane_input_tokens": None if control_plane_input_tokens is None else max(0, int(control_plane_input_tokens)),
        },
        "token_amplification_ratio": round(total / max(1, baseline_total), 4),
        "net_token_savings": net,
        "effective_token_savings_ratio": round(net / max(1, baseline_total), 4),
        "token_efficient": total <= baseline_total,
        "measurement": {
            "comparison_quality": comparison_quality,
            "baseline_tokens_source": str(baseline_tokens_source),
            "pipeline_input_tokens_source": str(pipeline_input_tokens_source),
            "pipeline_output_tokens_source": str(pipeline_output_tokens_source),
            "tokenizer": tokenizer,
            "tokenizer_exact": tokenizer_exact,
            "savings_claim_comparable": comparison_quality in {"comparable-estimates", "provider-reported"},
            "interpretation": interpretation,
        },
        "note": "This compares aggregate model-visible tokens. Local deterministic filtering/audit work consumes CPU but not model tokens.",
    }
