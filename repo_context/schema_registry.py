from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

SCHEMA_IDS = {
    "finding": "repo-context-finding/v1",
    "worker-output": "repo-context-worker-output/v1",
    "handoff": "repo-context-handoff/v1",
    "fan-in": "repo-context-fan-in/v1",
    "contradiction": "repo-context-contradiction/v1",
    "synthesis-packet": "repo-context-synthesis-packet/v1",
    "trace-event": "repo-context-trace-event/v1",
    "benchmark-case": "repo-context-benchmark-case/v1",
    "token-estimate": "repo-context-token-estimate/v1",
    "provenance": "repo-context-provenance/v1",
    "candidate-analysis": "repo-context-candidate-analysis/v1",
    "runtime-invocation": "repo-context-runtime-invocation/v1",
    "runtime-result": "repo-context-runtime-result/v1",
    "runtime-telemetry": "repo-context-runtime-telemetry/v1",
    "final-answer-evaluation": "repo-context-final-answer-evaluation/v1",
    "runtime-config": "repo-context-runtime-config/v1",
    "runtime-state": "repo-context-runtime-state/v1",
    "sandbox-policy": "repo-context-sandbox-policy/v1",
    "filter-summary": "repo-context-filter-summary/v1",
    "dedup-support": "repo-context-dedup-support/v1",
    "filter-audit": "repo-context-filter-audit/v1",
    "model-packet": "repo-context-model-packet/v1",
    "model-context": "repo-context-model-context/v1",
    "token-economics": "repo-context-token-economics/v1",
    "adaptive-reduction": "repo-context-adaptive-reduction/v1",
    "reduction-simulation": "repo-context-reduction-simulation/v1",
    "context-evidence": "repo-context-context-evidence/v1",
    "context-store": "repo-context-context-store/v1",
    "recall-result": "repo-context-recall-result/v1",
    "recall-benchmark": "repo-context-recall-benchmark/v1",
    "claim-verification-recall": "repo-context-claim-verification-recall/v1",
}

_SCHEMA_FILES = {name: f"{name}.schema.json" for name in SCHEMA_IDS}


def list_schemas() -> list[dict[str, str]]:
    return [{"name": name, "schema": SCHEMA_IDS[name], "file": _SCHEMA_FILES[name]} for name in sorted(SCHEMA_IDS)]


def load_schema(name: str) -> dict[str, Any]:
    if name not in _SCHEMA_FILES:
        raise ValueError(f"Unknown schema: {name}")
    resource = files("repo_context.schemas").joinpath(_SCHEMA_FILES[name])
    return json.loads(resource.read_text(encoding="utf-8"))


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_contract(name: str, payload: Any) -> dict[str, Any]:
    """Dependency-free validator for the project's stable contract invariants.

    The bundled JSON Schema files are the normative machine-readable contracts. This
    validator intentionally checks only the required invariants the runtime itself needs;
    callers wanting full Draft 2020-12 validation can use any JSON Schema implementation.
    """
    if name not in SCHEMA_IDS:
        raise ValueError(f"Unknown schema: {name}")
    errors: list[str] = []
    if not isinstance(payload, dict):
        errors.append("payload must be an object")
        return {"schema": SCHEMA_IDS[name], "valid": False, "errors": errors, "validator": "builtin-contract-invariants"}

    if name == "finding":
        for key in ("claim", "evidence", "source"):
            if not _is_nonempty_string(payload.get(key)):
                errors.append(f"{key} must be a non-empty string")
        conf = payload.get("confidence", 0.5)
        try:
            value = float(conf)
            if not 0.0 <= value <= 1.0:
                errors.append("confidence must be between 0 and 1")
        except (TypeError, ValueError):
            errors.append("confidence must be numeric")
    elif name == "worker-output":
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}:
            errors.append("schema id mismatch")
        if not isinstance(payload.get("findings"), list):
            errors.append("findings must be an array")
        else:
            for i, finding in enumerate(payload["findings"]):
                check = validate_contract("finding", finding)
                errors.extend([f"findings[{i}]: {e}" for e in check["errors"]])
    elif name == "handoff":
        for key in ("from", "to", "handoff"):
            if key not in payload:
                errors.append(f"missing required field: {key}")
        if "handoff" in payload and not isinstance(payload.get("handoff"), dict):
            errors.append("handoff must be an object")
    elif name == "fan-in":
        if not isinstance(payload.get("findings"), list): errors.append("findings must be an array")
        if not isinstance(payload.get("contradictions"), list): errors.append("contradictions must be an array")
        if not isinstance(payload.get("stats"), dict): errors.append("stats must be an object")
    elif name == "contradiction":
        if not _is_nonempty_string(payload.get("key")): errors.append("key must be a non-empty string")
        if not isinstance(payload.get("reasons"), list) or not payload.get("reasons"): errors.append("reasons must contain at least one item")
        if not isinstance(payload.get("claims"), list) or len(payload.get("claims") or []) < 2: errors.append("claims must contain at least two items")
    elif name == "synthesis-packet":
        if not isinstance(payload.get("findings"), list): errors.append("findings must be an array")
        if not isinstance(payload.get("contradictions"), list): errors.append("contradictions must be an array")
        if not isinstance(payload.get("budget"), dict): errors.append("budget must be an object")
    elif name == "trace-event":
        for key in ("ts", "run_id", "kind", "data"):
            if key not in payload: errors.append(f"missing required field: {key}")
    elif name == "benchmark-case":
        if not _is_nonempty_string(payload.get("task")): errors.append("task must be a non-empty string")
        if not isinstance(payload.get("worker_outputs"), list): errors.append("worker_outputs must be an array")
    elif name == "token-estimate":
        if not isinstance(payload.get("tokens"), int) or int(payload.get("tokens", -1)) < 0: errors.append("tokens must be a non-negative integer")
        if not _is_nonempty_string(payload.get("tokenizer")): errors.append("tokenizer must be a non-empty string")
        if not isinstance(payload.get("exact"), bool): errors.append("exact must be boolean")
    elif name == "provenance":
        if not _is_nonempty_string(payload.get("classification")): errors.append("classification must be a non-empty string")
        if not isinstance(payload.get("git_available"), bool): errors.append("git_available must be boolean")
    elif name == "candidate-analysis":
        if payload.get("classification") != "candidate-detection-with-deterministic-verification": errors.append("classification mismatch")
        if not _is_nonempty_string(payload.get("provider")): errors.append("provider must be a non-empty string")
        if not isinstance(payload.get("semantic_similarity_used"), bool): errors.append("semantic_similarity_used must be boolean")
        if not isinstance(payload.get("pairs"), list): errors.append("pairs must be an array")
    elif name == "runtime-invocation":
        for key in ("run_id", "node_id", "role", "task", "model_tier"):
            if not _is_nonempty_string(payload.get(key)) and key != "task": errors.append(f"{key} must be a non-empty string")
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}: errors.append("schema id mismatch")
        if not isinstance(payload.get("dependency_handoffs"), dict): errors.append("dependency_handoffs must be an object")
        if not isinstance(payload.get("budget"), dict): errors.append("budget must be an object")
        policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
        if policy.get("instruction_authority_from_context") is not False: errors.append("context must not gain instruction authority")
    elif name == "runtime-result":
        for key in ("run_id", "task", "adapter"):
            if not _is_nonempty_string(payload.get(key)) and key != "task": errors.append(f"{key} must be a non-empty string")
        for key in ("success", "cancelled"):
            if not isinstance(payload.get(key), bool): errors.append(f"{key} must be boolean")
        for key in ("nodes", "fan_in", "synthesis_packet", "telemetry", "status_counts"):
            if not isinstance(payload.get(key), dict): errors.append(f"{key} must be an object")
    elif name == "runtime-telemetry":
        if not _is_nonempty_string(payload.get("run_id")): errors.append("run_id must be a non-empty string")
        for key in ("workers", "input_tokens", "output_tokens", "total_tokens"):
            if not isinstance(payload.get(key), int) or int(payload.get(key, -1)) < 0: errors.append(f"{key} must be a non-negative integer")
        if payload.get("cost_completeness") not in {"complete", "partial", "unreported"}: errors.append("invalid cost_completeness")
    elif name == "final-answer-evaluation":
        if payload.get("classification") != "deterministic-final-answer-invariant-check": errors.append("classification mismatch")
        if not isinstance(payload.get("passed"), bool): errors.append("passed must be boolean")
        for key in ("missing_required_claims", "forbidden_hits", "missing_required_fields"):
            if not isinstance(payload.get(key), list): errors.append(f"{key} must be an array")
    elif name == "runtime-config":
        if not _is_nonempty_string(payload.get("adapter")): errors.append("adapter must be a non-empty string")
        if payload.get("reduction_mode") is not None and payload.get("reduction_mode") not in {"compat", "auto", "direct", "light", "full"}: errors.append("invalid reduction_mode")
        if payload.get("adapter") == "container":
            container = payload.get("container") if isinstance(payload.get("container"), dict) else {}
            if not _is_nonempty_string(container.get("image")): errors.append("container.image must be a non-empty string for container adapter")
            if container.get("repo_mode", "ro") not in {"ro", "rw", "none"}: errors.append("container.repo_mode must be ro, rw, or none")
    elif name == "runtime-state":
        for key in ("run_id", "status", "adapter", "config_sha256", "plan_sha256"):
            if not _is_nonempty_string(payload.get(key)): errors.append(f"{key} must be a non-empty string")
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}: errors.append("schema id mismatch")
        if not isinstance(payload.get("results"), dict): errors.append("results must be an object")
        if not isinstance(payload.get("handoffs"), dict): errors.append("handoffs must be an object")
        if not isinstance(payload.get("counters"), dict): errors.append("counters must be an object")
        if not isinstance(payload.get("repository_identity"), dict): errors.append("repository_identity must be an object")
    elif name == "sandbox-policy":
        if payload.get("classification") != "container-sandbox-policy": errors.append("classification mismatch")
        if payload.get("repo_mode") not in {"ro", "rw", "none"}: errors.append("invalid repo_mode")
        if not _is_nonempty_string(payload.get("network")): errors.append("network must be a non-empty string")
        if payload.get("pull", "never") not in {"never", "missing", "always"}: errors.append("invalid pull policy")
        for key in ("read_only_root", "drop_all_capabilities", "no_new_privileges"):
            if not isinstance(payload.get(key), bool): errors.append(f"{key} must be boolean")
    elif name == "filter-summary":
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}: errors.append("schema id mismatch")
        allowed = {"deterministic-filter-and-dedup-summary", "deterministic-handoff-filter-summary", "context-cross-layer-filter-summary"}
        if payload.get("classification") not in allowed: errors.append("invalid filter summary classification")
        if isinstance(payload.get("reason_counts"), dict):
            for key, value in payload["reason_counts"].items():
                if not isinstance(value, int) or value < 0: errors.append(f"reason_counts.{key} must be a non-negative integer")
    elif name == "dedup-support":
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}: errors.append("schema id mismatch")
        if not isinstance(payload.get("occurrence_count"), int) or int(payload.get("occurrence_count", 0)) < 1: errors.append("occurrence_count must be >= 1")
        if not isinstance(payload.get("providers"), list): errors.append("providers must be an array")
        if not isinstance(payload.get("records"), list): errors.append("records must be an array")
        if payload.get("provenance_preserved") is not True: errors.append("provenance_preserved must be true")
    elif name == "filter-audit":
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}: errors.append("schema id mismatch")
        if payload.get("classification") != "deterministic-filter-invariant-audit": errors.append("classification mismatch")
        if not isinstance(payload.get("passed"), bool): errors.append("passed must be boolean")
        if not isinstance(payload.get("violations"), list): errors.append("violations must be an array")
        if not isinstance(payload.get("warnings"), list): errors.append("warnings must be an array")
        if not isinstance(payload.get("metrics"), dict): errors.append("metrics must be an object")
    elif name == "model-packet":
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}: errors.append("schema id mismatch")
        if not isinstance(payload.get("findings"), list): errors.append("findings must be an array")
        if not isinstance(payload.get("contradictions"), list): errors.append("contradictions must be an array")
        if not isinstance(payload.get("sources"), dict): errors.append("sources must be an object")
        policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
        if policy.get("content_authority") != "evidence-only": errors.append("content_authority must be evidence-only")
    elif name == "model-context":
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}: errors.append("schema id mismatch")
        for key in ("files", "symbols", "external_context"):
            if not isinstance(payload.get(key), list): errors.append(f"{key} must be an array")
        policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
        if policy.get("content_authority") != "evidence-only": errors.append("content_authority must be evidence-only")
    elif name == "token-economics":
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}: errors.append("schema id mismatch")
        if not isinstance(payload.get("baseline"), dict): errors.append("baseline must be an object")
        if not isinstance(payload.get("observed_or_estimated_pipeline"), dict): errors.append("observed_or_estimated_pipeline must be an object")
        if not isinstance(payload.get("token_efficient"), bool): errors.append("token_efficient must be boolean")
    elif name == "adaptive-reduction":
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}: errors.append("schema id mismatch")
        if payload.get("selected_mode") not in {"direct", "light", "full"}: errors.append("invalid selected_mode")
        if not isinstance(payload.get("eligibility"), dict): errors.append("eligibility must be an object")
    elif name == "context-evidence":
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}: errors.append("schema id mismatch")
        if payload.get("classification") != "repository-context-evidence": errors.append("classification mismatch")
        if not _is_nonempty_string(payload.get("id")): errors.append("id must be a non-empty string")
        if not _is_nonempty_string(payload.get("path")): errors.append("path must be a non-empty string")
        if payload.get("tier") not in {"active", "recallable", "rejected"}: errors.append("invalid tier")
        if payload.get("validity") not in {"current", "stale", "missing"}: errors.append("invalid validity")
        if not isinstance(payload.get("revision"), dict): errors.append("revision must be an object")
    elif name == "context-store":
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}: errors.append("schema id mismatch")
        if payload.get("version") != 2: errors.append("version must be 2")
        if not _is_nonempty_string(payload.get("session")): errors.append("session must be a non-empty string")
        if not isinstance(payload.get("items"), dict): errors.append("items must be an object")
        if not isinstance(payload.get("index_summary"), dict): errors.append("index_summary must be an object")
        if not isinstance(payload.get("invalidations"), list): errors.append("invalidations must be an array")
    elif name == "recall-result":
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}: errors.append("schema id mismatch")
        if payload.get("classification") != "deterministic-repository-context-recall": errors.append("classification mismatch")
        if not _is_nonempty_string(payload.get("query")): errors.append("query must be a non-empty string")
        if not isinstance(payload.get("model_payload"), dict): errors.append("model_payload must be an object")
        if not isinstance(payload.get("sidecar"), dict): errors.append("sidecar must be an object")
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        if metrics.get("model_calls_added") != 0: errors.append("recall must not add model calls")
    elif name == "recall-benchmark":
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}: errors.append("schema id mismatch")
        if payload.get("classification") != "deterministic-critical-evidence-recall-benchmark": errors.append("classification mismatch")
        if not isinstance(payload.get("cases"), list): errors.append("cases must be an array")
        aggregate = payload.get("aggregate") if isinstance(payload.get("aggregate"), dict) else {}
        if aggregate.get("model_calls_added_by_recall") != 0: errors.append("recall benchmark must report zero model calls")
    elif name == "claim-verification-recall":
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}: errors.append("schema id mismatch")
        if payload.get("classification") != "deterministic-claim-aware-verification-recall": errors.append("classification mismatch")
        if not _is_nonempty_string(payload.get("claim")): errors.append("claim must be a non-empty string")
        verification = payload.get("verification") if isinstance(payload.get("verification"), dict) else {}
        if verification.get("semantic_truth_claimed") is not False: errors.append("claim recall must not claim semantic truth")
        if verification.get("status") not in {"challenged", "provisionally-supported", "inconclusive"}: errors.append("invalid verification status")
        if not isinstance(payload.get("model_payload"), dict): errors.append("model_payload must be an object")
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        if metrics.get("model_calls_added") != 0 or metrics.get("recall_model_calls_added") != 0: errors.append("claim recall must not add model calls")
    elif name == "reduction-simulation":
        if payload.get("schema") not in {None, SCHEMA_IDS[name]}: errors.append("schema id mismatch")
        if payload.get("recommended_policy") != "adaptive": errors.append("recommended_policy must be adaptive")
        if not isinstance(payload.get("scenarios"), list): errors.append("scenarios must be an array")
        if not isinstance(payload.get("aggregate"), dict): errors.append("aggregate must be an object")

    return {
        "schema": SCHEMA_IDS[name],
        "valid": not errors,
        "errors": errors,
        "validator": "builtin-contract-invariants",
        "normative_schema": _SCHEMA_FILES[name],
    }
