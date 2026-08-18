#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repo_context import __version__
from repo_context.adaptive_reduction import choose_reduction_mode
from repo_context.fan_in import reduce_worker_outputs
from repo_context.filter_audit import audit_filter_reduction
from repo_context.model_context import split_model_context, project_verification_context
from repo_context.model_packet import split_model_packet
from repo_context.runtime_adapters import CallableRuntimeAdapter, register_runtime_adapter, unregister_runtime_adapter
from repo_context.runtime_engine import execute_runtime
from repo_context.scenario_simulation import simulate_scenarios
from repo_context.schema_registry import list_schemas, load_schema, validate_contract
from repo_context.synthesis_packet import build_synthesis_packet
from repo_context.token_economics import summarize_token_economics


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    checks: dict[str, Any] = {"version": __version__}
    require(__version__ == "2.2.0", f"expected 2.2.0, got {__version__}")

    schemas = list_schemas()
    checks["schema_count"] = len(schemas)
    require(len(schemas) == 26, f"expected 26 schemas, got {len(schemas)}")

    jsonschema_status = "not-installed"
    draft_validator = None
    try:
        from jsonschema import Draft202012Validator
        draft_validator = Draft202012Validator
        for item in schemas:
            Draft202012Validator.check_schema(load_schema(item["name"]))
        jsonschema_status = "passed"
    except ImportError:
        pass
    checks["draft_2020_12_schema_structure"] = jsonschema_status

    def validate_normative(name: str, payload: dict[str, Any]) -> None:
        if draft_validator is not None:
            draft_validator(load_schema(name)).validate(payload)

    reduction = reduce_worker_outputs([
        {"worker": "a", "findings": [{"claim": "payment async", "evidence": "queue.publish", "source": "a.py", "canonicalKey": "payment|mode", "value": "async"}]},
        {"worker": "a", "findings": [{"claim": "payment async", "evidence": "queue.publish", "source": "a.py", "canonicalKey": "payment|mode", "value": "async"}]},
        {"worker": "b", "findings": [{"claim": "payment sync", "evidence": "legacy.write", "source": "b.py", "canonicalKey": "payment|mode", "value": "sync"}]},
    ])
    audit = audit_filter_reduction(reduction)
    require(audit.get("passed") is True, f"filter audit failed: {audit}")
    require(reduction["stats"]["contradiction_count"] == 1, "contradiction was not preserved")
    async_finding = next(x for x in reduction["findings"] if x.get("value") == "async")
    require(async_finding["reducer"]["agreement_count"] == 1, "same-worker repetition inflated agreement")
    packet = build_synthesis_packet(reduction, max_estimated_tokens=5000)
    packet["filter_audit"] = audit
    model_packet = split_model_packet(packet)
    require(validate_contract("model-packet", model_packet["model_payload"])["valid"], "model packet contract failed")
    validate_normative("model-packet", model_packet["model_payload"])
    require(model_packet["metrics"]["model_payload_tokens"] < model_packet["metrics"]["rich_packet_tokens"], "model packet did not get thinner")

    rich_context = {
        "repository_provenance": {"commit": "abc", "dirty": False},
        "trust_summary": {"blocks": 2},
        "files": [{"path": "a.py", "content": "def a(): return 1", "provenance": {"blob": "A"}}, {"path": "b.py", "content": "def b(): return 2", "provenance": {"blob": "B"}}],
        "symbols": [{"path": "a.py", "name": "a", "content": "return 1", "trust": {"instruction_authority": False}}, {"path": "b.py", "name": "b", "content": "return 2"}],
        "external_context": [],
    }
    model_context = split_model_context(rich_context)
    require(validate_contract("model-context", model_context["model_payload"])["valid"], "model context contract failed")
    validate_normative("model-context", model_context["model_payload"])
    require(model_context["metrics"]["model_context_tokens"] < model_context["metrics"]["rich_context_tokens"], "model context did not get thinner")
    verification = project_verification_context(rich_context, {"sources": {"S1": "b.py"}}, max_tokens=2000)
    require({x["path"] for x in verification["model_payload"]["files"]} == {"b.py"}, "grader verification context was not source-targeted")

    routes = {
        "low": choose_reduction_mode("bounded change", source_tokens=12000, complexity={"level": "focused"}, risk={"level": "low"})["selected_mode"],
        "medium": choose_reduction_mode("bounded change", source_tokens=12000, complexity={"level": "focused"}, risk={"level": "medium"})["selected_mode"],
        "high": choose_reduction_mode("bounded change", source_tokens=12000, complexity={"level": "focused"}, risk={"level": "high"})["selected_mode"],
    }
    require(routes == {"low": "direct", "medium": "light", "high": "full"}, f"risk routing drifted: {routes}")
    checks["risk_mode_matrix"] = routes
    validate_normative("adaptive-reduction", choose_reduction_mode("bounded change", source_tokens=12000, complexity={"level": "focused"}, risk={"level": "medium"}))

    simulation = simulate_scenarios()
    selected_modes = {x["selected_mode"] for x in simulation["scenarios"]}
    require(selected_modes == {"direct", "light", "full"}, f"default scenarios do not exercise all modes: {selected_modes}")
    aggregate = simulation["aggregate"]
    require(aggregate["adaptive_total_tokens"] <= aggregate["static_mode_total_tokens"]["full"], "adaptive simulation regressed beyond always-full")
    require(aggregate["static_mode_globally_eligible"]["direct"] is False, "direct unexpectedly became globally eligible")
    require(aggregate["static_mode_globally_eligible"]["full"] is True, "full must remain globally eligible")
    checks["scenario_aggregate"] = aggregate
    validate_normative("reduction-simulation", simulation)

    mixed = summarize_token_economics(
        aggregate_input_tokens=900, aggregate_output_tokens=100,
        baseline_input_tokens=1200, baseline_output_tokens=100,
        baseline_tokens_source="estimated", pipeline_input_tokens_source="provider-reported", pipeline_output_tokens_source="provider-reported",
    )
    require(mixed["measurement"]["comparison_quality"] == "mixed-measurement", "mixed token sources were presented as comparable")
    require(mixed["measurement"]["savings_claim_comparable"] is False, "mixed token sources incorrectly allow precise savings claim")
    validate_normative("token-economics", mixed)

    seen: list[dict[str, Any]] = []
    def adapter_fn(request: dict[str, Any], cancellation: Any) -> dict[str, Any]:
        seen.append(request)
        if request.get("role") == "grader":
            return {"decision": "pass", "score": 0.99, "failures": [], "evidence": ["verified"]}
        if request.get("role") == "integrator":
            return {"summary": "integrated", "findings": [{"claim": "payment mode reviewed", "evidence": "integrated", "source": "a.py"}]}
        return {"summary": "evidence", "findings": [{"claim": "payment async", "evidence": "queue.publish", "source": "a.py", "canonicalKey": "payment|mode", "value": "async"}]}

    register_runtime_adapter("release-gate", lambda cfg: CallableRuntimeAdapter("release-gate", adapter_fn))
    try:
        with tempfile.TemporaryDirectory() as td:
            result = execute_runtime(
                "compare conflicting independent evidence about payment behavior", td,
                runtime_config={"adapter": "release-gate", "max_attempts": 1}, adapter_name="release-gate",
                context_pack=rich_context, context_tokens=6000, output_tokens=3000, model_calls=8,
                reduction_mode="auto", checkpoint=False,
            )
    finally:
        unregister_runtime_adapter("release-gate")
    require(result["success"] is True, "adaptive runtime release smoke failed")
    validate_normative("runtime-result", result)
    validate_normative("runtime-telemetry", result["telemetry"])
    require(result["plan"]["adaptive_reduction"]["effective_mode"] == "full", "explicit conflict did not force full")
    graders = [x for x in seen if x.get("role") == "grader"]
    integrators = [x for x in seen if x.get("role") == "integrator"]
    require(graders and graders[0].get("repository_context_mode") == "source-targeted-verification", "grader did not use targeted verification context")
    require(integrators and integrators[0].get("context") is None, "integrator received duplicate repository context")
    checks["runtime"] = {
        "success": True,
        "mode": result["plan"]["adaptive_reduction"]["effective_mode"],
        "calls": result["backpressure"]["model_calls_used"],
        "peak_parallel": result["backpressure"]["peak_active_workers"],
        "filter_audit": result["filter_audit"]["passed"],
        "token_measurement_quality": result["token_economics"]["measurement"]["comparison_quality"],
    }
    checks["representative_payload_jsonschema_validation"] = "passed" if draft_validator is not None else "not-installed"

    print(json.dumps({"release_gate": "passed", "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
