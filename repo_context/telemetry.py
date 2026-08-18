from __future__ import annotations

import json
import pathlib
import time
from typing import Any

from .storage import prepare_state_dir, state_dir
from .tokenizer import count_tokens
from .token_economics import request_token_breakdown


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_usage(
    result: dict[str, Any],
    *,
    request: dict[str, Any],
    tokenizer: str = "native",
    tokenizer_model: str | None = None,
) -> dict[str, Any]:
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    payload = result.get("payload")
    reported_input = usage.get("input_tokens")
    reported_output = usage.get("output_tokens")
    input_tokens = int(reported_input) if isinstance(reported_input, int) and reported_input >= 0 else count_tokens(request, tokenizer=tokenizer, model=tokenizer_model)
    output_tokens = int(reported_output) if isinstance(reported_output, int) and reported_output >= 0 else count_tokens(payload, tokenizer=tokenizer, model=tokenizer_model)
    cost = _number(usage.get("cost_usd"))
    breakdown = request_token_breakdown(request, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "input_tokens_source": "provider-reported" if isinstance(reported_input, int) and reported_input >= 0 else "estimated",
        "output_tokens_source": "provider-reported" if isinstance(reported_output, int) and reported_output >= 0 else "estimated",
        "cost_usd": cost,
        "cost_source": "provider-reported" if cost is not None else "unreported",
        "latency_ms": float(result.get("latency_ms") or 0.0),
        "model": usage.get("model"),
        "provider": usage.get("provider"),
        "tokenizer": tokenizer,
        "tokenizer_model": tokenizer_model,
        "request_token_breakdown": breakdown,
        "note": "Cost is never inferred from a static price table; it is present only when the runtime/provider reports it. Data/control-plane token split is an estimated request decomposition.",
    }


class RuntimeTelemetry:
    def __init__(self, root: pathlib.Path, run_id: str, *, load_existing: bool = False):
        self.root = root
        self.run_id = run_id
        self.path = state_dir(root) / "telemetry" / f"{run_id}.jsonl"
        self.events: list[dict[str, Any]] = []
        if load_existing:
            try:
                for line in self.path.read_text(encoding="utf-8").splitlines():
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row, dict) and row.get("run_id") == run_id:
                        self.events.append(row)
            except OSError:
                pass

    def record(self, event: dict[str, Any]) -> None:
        payload = {"ts": time.time(), "run_id": self.run_id, **event}
        self.events.append(payload)
        prepare_state_dir(self.root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")

    def summary(self) -> dict[str, Any]:
        worker_events = [x for x in self.events if x.get("kind") == "worker"]
        usage = [x.get("usage", {}) for x in worker_events if isinstance(x.get("usage"), dict)]
        reported_costs = [float(u["cost_usd"]) for u in usage if u.get("cost_usd") is not None]

        def source_summary(field: str) -> str:
            values = {str(u.get(field) or "estimated") for u in usage}
            if not values or values == {"estimated"}:
                return "estimated"
            if values == {"provider-reported"}:
                return "provider-reported"
            return "mixed"

        return {
            "schema": "repo-context-runtime-telemetry/v1",
            "run_id": self.run_id,
            "workers": len({str(x.get("node_id")) for x in worker_events}),
            "attempts": len(worker_events),
            "status_counts": {
                status: sum(1 for x in worker_events if x.get("status") == status)
                for status in sorted({str(x.get("status")) for x in worker_events})
            },
            "input_tokens": sum(int(u.get("input_tokens", 0)) for u in usage),
            "output_tokens": sum(int(u.get("output_tokens", 0)) for u in usage),
            "input_tokens_source": source_summary("input_tokens_source"),
            "output_tokens_source": source_summary("output_tokens_source"),
            "total_tokens": sum(int(u.get("total_tokens", 0)) for u in usage),
            "request_estimated_input_tokens": sum(int((u.get("request_token_breakdown") or {}).get("total_input_tokens_estimated", 0)) for u in usage),
            "data_plane_input_tokens_estimated": sum(int((u.get("request_token_breakdown") or {}).get("data_plane_tokens_estimated", 0)) for u in usage),
            "control_plane_input_tokens_estimated": sum(int((u.get("request_token_breakdown") or {}).get("control_plane_tokens_estimated", 0)) for u in usage),
            "latency_ms_sum": round(sum(float(u.get("latency_ms", 0.0)) for u in usage), 2),
            "reported_cost_usd": round(sum(reported_costs), 8) if reported_costs else None,
            "reported_cost_samples": len(reported_costs),
            "cost_completeness": "complete" if reported_costs and len(reported_costs) == len(usage) else "partial" if reported_costs else "unreported",
            "path": str(self.path),
        }
