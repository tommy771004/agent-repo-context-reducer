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


def _raw_source_estimate(index: dict[str, Any]) -> int:
    return sum(estimate_tokens_from_bytes(int(f.get("bytes", 0))) for f in index.get("files", []))


def _json_tokens(value: Any) -> int:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return estimate_tokens_from_bytes(len(raw))


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
                     min_confidence: float = 0.0) -> dict[str, Any]:
    raw_tokens = _json_tokens(worker_outputs)

    started = time.perf_counter()
    reduction = reduce_worker_outputs(worker_outputs, min_confidence=min_confidence)
    reduction_ms = round((time.perf_counter() - started) * 1000, 3)

    started = time.perf_counter()
    packet = build_synthesis_packet(reduction, max_estimated_tokens=synthesis_budget)
    packet_ms = round((time.perf_counter() - started) * 1000, 3)

    reduced_payload_tokens = _json_tokens({
        "findings": reduction.get("findings", []),
        "contradictions": reduction.get("contradictions", []),
    })
    synthesis_tokens = int(packet.get("budget", {}).get("estimated_tokens") or _json_tokens(packet))

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
