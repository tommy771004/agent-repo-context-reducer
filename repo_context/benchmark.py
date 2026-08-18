from __future__ import annotations

import json
import pathlib
import time
from typing import Any

from .context_planner import build_context
from .fan_in import reduce_worker_outputs
from .indexer import ensure_index
from .synthesis_packet import build_synthesis_packet
from .util import estimate_tokens_from_bytes
from .tokenizer import count_tokens, get_tokenizer


def _raw_source_estimate(index: dict[str, Any]) -> int:
    return sum(estimate_tokens_from_bytes(int(f.get("bytes", 0))) for f in index.get("files", []))


def _json_tokens(value: Any, *, tokenizer: str = "native", tokenizer_model: str | None = None) -> int:
    return count_tokens(value, tokenizer=tokenizer, model=tokenizer_model)


def benchmark_tasks(root: pathlib.Path, tasks: list[dict[str, Any]], budget: int = 6000) -> dict[str, Any]:
    index = ensure_index(root, sync=True)["index"]
    raw = _raw_source_estimate(index)
    rows = []
    for i, task in enumerate(tasks):
        text = str(task.get("task", ""))
        pack = build_context(index, text, budget=budget, session=f"benchmark-{i}")
        selected_paths = {f.get("path") for f in pack.get("files", [])} | {s.get("path") for s in pack.get("symbols", [])}
        expected = set(task.get("expected_paths", []))
        recall = None if not expected else len(expected & selected_paths) / len(expected)
        used = int(pack["budget"]["estimated_used_tokens"])
        rows.append({
            "task": text,
            "raw_repository_token_estimate": raw,
            "context_token_estimate": used,
            "structural_reduction_ratio": None if raw <= 0 else round(1 - used / raw, 4),
            "selected_paths": sorted(p for p in selected_paths if p),
            "expected_path_recall": None if recall is None else round(recall, 4),
            "correctness_claim": False,
        })
    return {
        "tasks": rows,
        "metrics": {
            "token_estimator": "utf8-bytes/4",
            "correctness": "not-measured unless expected_paths are supplied; path recall is not answer correctness",
        },
    }


def benchmark_fan_in(worker_outputs: list[Any], *, synthesis_budget: int = 6000,
                     min_confidence: float = 0.0, tokenizer: str = "native",
                     tokenizer_model: str | None = None) -> dict[str, Any]:
    raw_tokens = _json_tokens(worker_outputs, tokenizer=tokenizer, tokenizer_model=tokenizer_model)

    started = time.perf_counter()
    reduction = reduce_worker_outputs(worker_outputs, min_confidence=min_confidence, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
    reduction_ms = round((time.perf_counter() - started) * 1000, 3)

    started = time.perf_counter()
    packet = build_synthesis_packet(reduction, max_estimated_tokens=synthesis_budget, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
    packet_ms = round((time.perf_counter() - started) * 1000, 3)

    reduced_payload_tokens = _json_tokens({
        "findings": reduction.get("findings", []),
        "contradictions": reduction.get("contradictions", []),
    }, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
    synthesis_tokens = int(packet.get("budget", {}).get("estimated_tokens") or _json_tokens(packet, tokenizer=tokenizer, tokenizer_model=tokenizer_model))

    return {
        "schema": "repo-context-fan-in-benchmark/v1",
        "metrics": {
            "raw_worker_output_tokens": raw_tokens,
            "fan_in_reduced_tokens": reduced_payload_tokens,
            "synthesis_packet_tokens": synthesis_tokens,
            "fan_in_reduction_ratio": round(1 - (reduced_payload_tokens / max(1, raw_tokens)), 4),
            "end_to_end_context_reduction_ratio": round(1 - (synthesis_tokens / max(1, raw_tokens)), 4),
            "reducer_latency_ms": reduction_ms,
            "packet_builder_latency_ms": packet_ms,
            "worker_output_count": reduction.get("stats", {}).get("worker_output_count", 0),
            "duplicate_count": reduction.get("stats", {}).get("duplicate_count", 0),
            "agreement_group_count": reduction.get("stats", {}).get("agreement_group_count", 0),
            "contradiction_count": reduction.get("stats", {}).get("contradiction_count", 0),
            "malformed_count": reduction.get("stats", {}).get("malformed_count", 0),
            "budget_overflow": bool(packet.get("budget", {}).get("overflow")),
            "tokenizer": get_tokenizer(tokenizer, model=tokenizer_model).name,
            "tokenizer_exact": bool(get_tokenizer(tokenizer, model=tokenizer_model).exact),
            "tokenizer_model": tokenizer_model,
        },
        "unmeasured_host_metrics": {
            "worker_latency_ms": None,
            "synthesis_latency_ms": None,
            "model_cost": None,
            "human_escalated": None,
            "final_task_correctness": None,
        },
        "notes": [
            "Deterministic reducer timings are measured locally.",
            "Model latency, provider billing, escalation, and answer correctness require host/runtime instrumentation and are intentionally not fabricated.",
        ],
    }


def load_tasks(path: pathlib.Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict) and x.get("task")]
    raise ValueError("benchmark task file must be a JSON array")


def benchmark_reducer_cases(cases: list[dict[str, Any]], *, default_synthesis_budget: int = 6000,
                            tokenizer: str = "native", tokenizer_model: str | None = None) -> dict[str, Any]:
    """Measure deterministic reducer correctness across complete worker->fan-in->packet cases.

    This is an end-to-end benchmark for the deterministic context pipeline. It does not
    claim to measure the correctness of a downstream model's prose answer.
    """
    from .contradiction import normalize_identity_text
    from .schema_registry import validate_contract

    rows: list[dict[str, Any]] = []
    for i, case in enumerate(cases):
        contract = validate_contract("benchmark-case", case)
        if not contract["valid"]:
            rows.append({
                "case": i,
                "task": str(case.get("task", "")) if isinstance(case, dict) else "",
                "passed": False,
                "contract_errors": contract["errors"],
            })
            continue

        worker_outputs = list(case.get("worker_outputs") or [])
        budget = int(case.get("synthesis_budget") or default_synthesis_budget)
        started = time.perf_counter()
        reduction = reduce_worker_outputs(worker_outputs, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
        packet = build_synthesis_packet(reduction, max_estimated_tokens=budget, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)

        output_claims = {normalize_identity_text(f.get("claim")) for f in packet.get("findings", [])}
        required = {normalize_identity_text(x) for x in case.get("required_claims", []) if str(x).strip()}
        forbidden = {normalize_identity_text(x) for x in case.get("forbidden_claims", []) if str(x).strip()}
        missing_required = sorted(required - output_claims)
        present_forbidden = sorted(forbidden & output_claims)

        observed_sources: set[str] = set()
        for finding in packet.get("findings", []):
            if finding.get("source"):
                observed_sources.add(str(finding["source"]))
            reducer = finding.get("reducer") if isinstance(finding.get("reducer"), dict) else {}
            observed_sources.update(str(x) for x in reducer.get("supporting_sources", []) if x)
        required_sources = {str(x) for x in case.get("required_sources", []) if str(x)}
        missing_sources = sorted(required_sources - observed_sources)

        expected_contradictions = case.get("expected_contradiction_count")
        observed_contradictions = len(packet.get("contradictions", []))
        contradiction_match = (
            True if expected_contradictions is None else observed_contradictions == int(expected_contradictions)
        )
        max_malformed = case.get("max_malformed_count")
        observed_malformed = int(reduction.get("stats", {}).get("malformed_count", 0))
        malformed_match = True if max_malformed is None else observed_malformed <= int(max_malformed)
        passed = not missing_required and not present_forbidden and not missing_sources and contradiction_match and malformed_match

        rows.append({
            "case": i,
            "task": str(case.get("task", "")),
            "passed": passed,
            "missing_required_claims": missing_required,
            "present_forbidden_claims": present_forbidden,
            "missing_required_sources": missing_sources,
            "expected_contradiction_count": expected_contradictions,
            "observed_contradiction_count": observed_contradictions,
            "contradiction_match": contradiction_match,
            "observed_malformed_count": observed_malformed,
            "malformed_match": malformed_match,
            "budget_overflow": bool(packet.get("budget", {}).get("overflow")),
            "synthesis_packet_tokens": int(packet.get("budget", {}).get("estimated_tokens", 0)),
            "pipeline_latency_ms": elapsed_ms,
        })

    passed = sum(1 for row in rows if row.get("passed"))
    return {
        "schema": "repo-context-e2e-benchmark/v1",
        "classification": "deterministic-worker-to-synthesis-packet-correctness",
        "cases": rows,
        "summary": {
            "case_count": len(rows),
            "passed": passed,
            "failed": len(rows) - passed,
            "pass_rate": round(passed / max(1, len(rows)), 4),
        },
        "correctness_scope": "Reducer/context-packet invariants only; downstream model answer correctness is not measured.",
        "tokenizer": {
            "name": get_tokenizer(tokenizer, model=tokenizer_model).name,
            "exact": bool(get_tokenizer(tokenizer, model=tokenizer_model).exact),
            "model": tokenizer_model,
        },
    }


def load_benchmark_cases(path: pathlib.Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("benchmark case file must be a JSON array")
    return [x for x in data if isinstance(x, dict)]
