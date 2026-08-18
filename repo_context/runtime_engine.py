from __future__ import annotations

import concurrent.futures
import json
import pathlib
import threading
import time
from typing import Any

from .answer_evaluation import evaluate_final_answer
from .handoff import reduce_handoff
from .grader import evaluate_grade
from .model_router import stronger
from .orchestration import plan_harness
from .runtime_adapters import CancellationToken, build_runtime_invocation, resolve_runtime_adapter
from .runtime_context import slice_context_pack
from .synthesis_packet import build_synthesis_packet
from .model_packet import split_model_packet
from .model_context import split_model_context, project_verification_context
from .token_economics import summarize_token_economics
from .adaptive_reduction import choose_reduction_mode, adapt_schedule
from .lane_budget import allocate_lane_budgets, optimize_model_plane_context_budgets
from .fan_in import reduce_worker_outputs
from .filter_audit import audit_filter_reduction
from .telemetry import RuntimeTelemetry, normalize_usage
from .tokenizer import count_tokens, get_tokenizer
from .trace import Trace, new_run_id
from .schema_registry import validate_contract
from .runtime_state import RuntimeCheckpointStore, config_fingerprint, fingerprint, repository_runtime_identity


def load_runtime_config(path_or_json: str | pathlib.Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(path_or_json, dict):
        data = dict(path_or_json)
    else:
        p = pathlib.Path(path_or_json)
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
        else:
            data = json.loads(str(path_or_json))
    if not isinstance(data, dict):
        raise ValueError("runtime config must be a JSON object")
    validation = validate_contract("runtime-config", data)
    if not validation["valid"]:
        raise ValueError("invalid runtime config: " + "; ".join(validation["errors"]))
    return data


def _model_tier_for_role(model_policy: dict[str, Any], role: str) -> str:
    roles = model_policy.get("roles", {})
    alias = role
    if role in {"implementer", "tester"}:
        alias = "worker"
    elif role in {"grader", "reviewer", "verifier", "security-reviewer"}:
        alias = "grader"
    return str(roles.get(alias, roles.get("worker", "standard")))


def _lane_for_node(lane_budget: dict[str, Any], node_id: str) -> dict[str, Any]:
    for lane in lane_budget.get("lanes", []):
        if str(lane.get("id")) == node_id:
            return lane
    return {}


def _worker_finding_envelope(node: dict[str, Any], payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("findings"), list):
        body = dict(payload)
        body.setdefault("worker_id", str(node.get("id") or "worker"))
        body.setdefault("role", str(node.get("role") or "worker"))
        return body
    finding = {
        "claim": str(payload.get("summary") or payload.get("result") or payload) if isinstance(payload, dict) else str(payload),
        "evidence": json.dumps(payload, ensure_ascii=False, default=str)[:4000] if not isinstance(payload, str) else payload[:4000],
        "source": f"runtime:{node.get('id','worker')}",
        "confidence": 0.5,
    }
    return {"worker_id": str(node.get("id") or "worker"), "role": str(node.get("role") or "worker"), "findings": [finding]}


def _checkpoint_safe_result(result: dict[str, Any], max_payload_bytes: int) -> dict[str, Any]:
    out = dict(result)
    payload = out.get("payload")
    try:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    except (TypeError, ValueError):
        raw = b""
    if raw and len(raw) > max(0, int(max_payload_bytes)):
        out["payload"] = None
        out["checkpoint_payload_omitted"] = True
        out["checkpoint_payload_bytes"] = len(raw)
    return out


def _checkpoint_worker_output(payload: dict[str, Any], *, max_findings: int = 100, evidence_chars: int = 4000) -> dict[str, Any]:
    out = {k: v for k, v in payload.items() if k != "findings"}
    rows = []
    for finding in (payload.get("findings") or [])[:max(1, int(max_findings))]:
        if not isinstance(finding, dict):
            continue
        row = dict(finding)
        if isinstance(row.get("evidence"), str):
            row["evidence"] = row["evidence"][:max(1, int(evidence_chars))]
        rows.append(row)
    out["findings"] = rows
    out["checkpoint_truncated"] = len(payload.get("findings") or []) > len(rows)
    return out


def execute_runtime(
    task: str,
    repo: pathlib.Path | str,
    *,
    runtime_config: dict[str, Any],
    adapter_name: str | None = None,
    forced_type: str | None = None,
    context_pack: dict[str, Any] | None = None,
    context_tokens: int = 12000,
    output_tokens: int = 4000,
    model_calls: int = 10,
    concurrency: int = 2,
    authorize_external: bool = False,
    authorize_network: bool = False,
    authorize_write: bool = False,
    fail_fast: bool = True,
    resume: bool = False,
    allow_repo_drift: bool = False,
    checkpoint: bool = True,
    run_id: str | None = None,
    tokenizer: str = "native",
    tokenizer_model: str | None = None,
    synthesis_budget: int = 6000,
    final_answer_case: dict[str, Any] | None = None,
    reduction_mode: str | None = None,
) -> dict[str, Any]:
    root = pathlib.Path(repo).resolve()
    if resume and not run_id:
        raise ValueError("resume requires an existing run_id")
    run_id = run_id or new_run_id()
    adapter_id = adapter_name or str(runtime_config.get("adapter") or "subprocess")
    adapter = resolve_runtime_adapter(
        adapter_id, runtime_config, authorize_external=authorize_external,
        authorize_network=authorize_network, authorize_write=authorize_write,
    )
    plan = plan_harness(
        task,
        root,
        forced_type=forced_type,
        context_tokens=context_tokens,
        output_tokens=output_tokens,
        model_calls=model_calls,
    )
    requested_reduction_mode = str(reduction_mode or runtime_config.get("reduction_mode") or "compat")
    if requested_reduction_mode not in {"compat", "auto", "direct", "light", "full"}:
        raise ValueError("reduction_mode must be compat, auto, direct, light, or full")
    pre_context_split = split_model_context(context_pack, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
    pre_source_tokens = count_tokens({"task": task, "context_pack": pre_context_split["model_payload"]}, tokenizer=tokenizer, model=tokenizer_model)
    pre_reduction_decision = choose_reduction_mode(
        task, source_tokens=pre_source_tokens, duplicate_ratio=0.0, conflict_ratio=0.0,
        task_type=plan.get("schedule", {}).get("task_type"), complexity=plan.get("complexity"), risk=plan.get("risk"),
        requires_parallel_evidence=bool(plan.get("complexity", {}).get("multi_agent_recommended")),
    )
    effective_reduction_mode = pre_reduction_decision["selected_mode"] if requested_reduction_mode == "auto" else requested_reduction_mode
    if effective_reduction_mode != "compat":
        eligibility = pre_reduction_decision["eligibility"].get(effective_reduction_mode, {})
        if eligibility.get("eligible") is not True:
            blocked = ", ".join(eligibility.get("blocked_by") or []) or "policy"
            raise ValueError(f"reduction mode {effective_reduction_mode} is not eligible for this task: {blocked}")
        plan["schedule"] = adapt_schedule(plan["schedule"], effective_reduction_mode, requires_parallel_evidence=bool(pre_reduction_decision["inputs"].get("requires_parallel_evidence")))
        plan["lane_budget"] = allocate_lane_budgets(
            plan["schedule"], plan["model_policy"], context_tokens=context_tokens, output_tokens=output_tokens, model_calls=model_calls
        )
        plan["lane_budget"] = optimize_model_plane_context_budgets(
            plan["lane_budget"], mode=effective_reduction_mode
        )
    plan["adaptive_reduction"] = {
        **pre_reduction_decision,
        "requested_mode": requested_reduction_mode,
        "effective_mode": effective_reduction_mode,
        "enforced": effective_reduction_mode != "compat",
    }
    schedule = plan["schedule"]
    node_map = {str(n["id"]): n for n in schedule.get("nodes", [])}
    cancellation = CancellationToken()
    trace = Trace(root, run_id)
    telemetry = RuntimeTelemetry(root, run_id, load_existing=resume)
    store = RuntimeCheckpointStore(root, run_id)
    checkpoint_enabled = bool(checkpoint and runtime_config.get("checkpoint", True))
    cfg_sha = config_fingerprint(runtime_config)
    plan_sha = fingerprint(plan)
    repo_identity = repository_runtime_identity(root)
    resume_settings = {
        "forced_type": forced_type, "context_tokens": int(context_tokens), "output_tokens": int(output_tokens),
        "model_calls": int(model_calls), "tokenizer": tokenizer, "tokenizer_model": tokenizer_model,
        "synthesis_budget": int(synthesis_budget), "fail_fast": bool(fail_fast), "reduction_mode": requested_reduction_mode,
        "context_present": context_pack is not None,
    }
    resume_settings_sha = fingerprint(resume_settings)
    started = time.perf_counter()
    results: dict[str, dict[str, Any]] = {}
    handoffs: dict[str, dict[str, Any]] = {}
    worker_outputs: dict[str, dict[str, Any]] = {}
    execution_waves: list[dict[str, Any]] = []
    max_concurrency = max(1, int(concurrency))
    runtime_wall_seconds = max(1.0, float(runtime_config.get("wall_seconds", 900)))
    state_lock = threading.Lock()
    active_workers = 0
    peak_active_workers = 0
    model_call_count = 0
    consumed_input_tokens = 0
    consumed_output_tokens = 0
    budget_exhausted: list[str] = []
    budget_overshoot: list[str] = []
    previous_elapsed_ms = 0.0
    resume_count = 0
    created_at = int(time.time())

    if resume:
        previous = store.load()
        if previous.get("task") != task:
            raise ValueError("runtime resume task does not match checkpoint")
        if previous.get("adapter") != adapter_id:
            raise ValueError("runtime resume adapter does not match checkpoint")
        if previous.get("config_sha256") != cfg_sha:
            raise ValueError("runtime resume config fingerprint does not match checkpoint")
        if previous.get("plan_sha256") != plan_sha:
            raise ValueError("runtime resume plan fingerprint does not match checkpoint")
        if previous.get("resume_settings_sha256") != resume_settings_sha:
            raise ValueError("runtime resume budget/tokenizer policy does not match checkpoint")
        saved_repo = previous.get("repository_identity") if isinstance(previous.get("repository_identity"), dict) else {}
        saved_fp = saved_repo.get("fingerprint")
        current_fp = repo_identity.get("fingerprint")
        if saved_fp and current_fp and saved_fp != current_fp and not allow_repo_drift:
            raise ValueError("repository drift detected since checkpoint; pass allow_repo_drift only after reviewing the change")
        results = {str(k): dict(v) for k, v in (previous.get("results") or {}).items() if isinstance(v, dict)}
        handoffs = {str(k): dict(v) for k, v in (previous.get("handoffs") or {}).items() if isinstance(v, dict)}
        worker_outputs = {str(k): dict(v) for k, v in (previous.get("worker_outputs") or {}).items() if isinstance(v, dict)}
        execution_waves = list(previous.get("execution_waves") or [])
        counters = previous.get("counters") if isinstance(previous.get("counters"), dict) else {}
        model_call_count = int(counters.get("model_calls", 0))
        consumed_input_tokens = int(counters.get("input_tokens", 0))
        consumed_output_tokens = int(counters.get("output_tokens", 0))
        previous_elapsed_ms = float(previous.get("elapsed_ms_total", 0.0))
        budget_exhausted = list(previous.get("budget_exhausted") or [])
        budget_overshoot = list(previous.get("budget_overshoot") or [])
        resume_count = int(previous.get("resume_count", 0)) + 1
        created_at = int(previous.get("created_at", created_at))
        trace.event("runtime-resume", {"run_id": run_id, "resume_count": resume_count, "repository_drift_allowed": allow_repo_drift})

    remaining_wall_seconds = runtime_wall_seconds - previous_elapsed_ms / 1000.0
    deadline = time.monotonic() + max(0.0, remaining_wall_seconds)
    if remaining_wall_seconds <= 0:
        if "wall_seconds" not in budget_exhausted:
            budget_exhausted.append("wall_seconds")
        cancellation.cancel()

    def persist_checkpoint(status: str, *, final_summary: dict[str, Any] | None = None) -> None:
        if not checkpoint_enabled:
            return
        max_payload = max(0, int(runtime_config.get("checkpoint_payload_bytes", 250_000)))
        state = {
            "status": status, "task": task, "adapter": adapter_id, "created_at": created_at,
            "resume_count": resume_count, "config_sha256": cfg_sha, "plan_sha256": plan_sha,
            "resume_settings": resume_settings, "resume_settings_sha256": resume_settings_sha,
            "repository_identity": repo_identity,
            "results": {k: _checkpoint_safe_result(v, max_payload) for k, v in results.items()},
            "handoffs": handoffs, "worker_outputs": worker_outputs, "execution_waves": execution_waves,
            "counters": {"model_calls": model_call_count, "input_tokens": consumed_input_tokens, "output_tokens": consumed_output_tokens},
            "budget_exhausted": list(budget_exhausted), "budget_overshoot": list(budget_overshoot),
            "elapsed_ms_total": round(previous_elapsed_ms + (time.perf_counter() - started) * 1000, 2),
            "authorization": {"external": authorize_external, "network": authorize_network, "repository_write": authorize_write},
            "final_answer_case": final_answer_case,
            "final_summary": final_summary,
        }
        store.save(state)

    persist_checkpoint("resuming" if resume else "running")
    trace.event("runtime-start", {"adapter": adapter_id, "schedule": schedule, "concurrency": max_concurrency, "resume": resume})

    def current_synthesis_packet() -> dict[str, Any] | None:
        rows = list(worker_outputs.values())
        if not rows:
            return None
        reduced = reduce_worker_outputs(rows, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
        audit = audit_filter_reduction(reduced)
        if not audit.get("passed"):
            raise RuntimeError("filter/dedup invariant audit failed before synthesis: " + "; ".join(audit.get("violations") or []))
        packet = build_synthesis_packet(
            reduced,
            max_estimated_tokens=max(1, int(synthesis_budget)),
            tokenizer=tokenizer,
            tokenizer_model=tokenizer_model,
        )
        packet["filter_audit"] = audit
        return split_model_packet(packet, tokenizer=tokenizer, tokenizer_model=tokenizer_model)["model_payload"]

    def invoke_node(node_id: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
        nonlocal active_workers, peak_active_workers, model_call_count, consumed_input_tokens, consumed_output_tokens
        node = node_map[node_id]
        full_dependency_handoffs = {dep: handoffs[dep] for dep in node.get("depends_on", []) if dep in handoffs}
        model_tier = _model_tier_for_role(plan["model_policy"], str(node.get("role") or "worker"))
        lane = _lane_for_node(plan["lane_budget"], node_id)
        retry_cfg = plan.get("retry_policy", {})
        role = str(node.get("role") or "worker")
        # Grader/integrator consume the canonical synthesis packet. Re-sending full handoffs
        # duplicates the same evidence and inflates both token usage and apparent support.
        if role in {"grader", "integrator"}:
            dependency_handoffs = {
                dep: {
                    "status": results.get(dep, {}).get("status"),
                    "handoff_available": dep in handoffs,
                    "role": node_map.get(dep, {}).get("role"),
                }
                for dep in node.get("depends_on", [])
            }
        else:
            dependency_handoffs = full_dependency_handoffs
        default_attempts = 1 if role in {"grader", "integrator"} else int(retry_cfg.get("max_worker_attempts", 1))
        max_attempts = max(1, int(runtime_config.get("max_attempts", default_attempts)))
        if not bool(runtime_config.get("retry_failed_workers", True)):
            max_attempts = 1
        current_tier = model_tier
        last_result: dict[str, Any] = {"status": "failed", "reason": "not-invoked", "payload": None}
        last_request: dict[str, Any] = {}
        attempts: list[dict[str, Any]] = []
        with state_lock:
            active_workers += 1
            peak_active_workers = max(peak_active_workers, active_workers)
        try:
            for attempt in range(1, max_attempts + 1):
                if cancellation.cancelled or time.monotonic() >= deadline:
                    last_result = {"status": "cancelled", "reason": "runtime-cancellation-requested", "payload": None}
                    break
                with state_lock:
                    exhausted_before_call = []
                    if model_call_count >= int(model_calls): exhausted_before_call.append("model_calls")
                    if consumed_input_tokens >= int(context_tokens): exhausted_before_call.append("context_tokens")
                    if consumed_output_tokens >= int(output_tokens): exhausted_before_call.append("output_tokens")
                    if exhausted_before_call:
                        for key in exhausted_before_call:
                            if key not in budget_exhausted: budget_exhausted.append(key)
                        last_result = {"status": "blocked", "reason": "runtime-budget-exhausted", "exhausted": exhausted_before_call, "payload": None}
                        cancellation.cancel()
                        break
                    model_call_count += 1
                lane_context_limit = max(0, int(lane.get("context_tokens", 0)))
                synthesis_for_role = current_synthesis_packet() if role in {"grader", "integrator"} else None
                lane_context = None
                verification_context_metrics = None
                if role == "grader":
                    verification = project_verification_context(
                        context_pack, synthesis_for_role, max_tokens=lane_context_limit,
                        tokenizer=tokenizer, tokenizer_model=tokenizer_model,
                    )
                    model_lane_context = verification["model_payload"]
                    verification_context_metrics = verification["metrics"]
                elif role == "integrator":
                    # The integrator receives the canonical thin synthesis packet. Re-sending
                    # repository context here duplicates the exact evidence it is integrating.
                    model_lane_context = None
                else:
                    lane_context = slice_context_pack(
                        context_pack,
                        lane_context_limit,
                        tokenizer=tokenizer,
                        tokenizer_model=tokenizer_model,
                    )
                    lane_context_split = split_model_context(lane_context, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
                    model_lane_context = lane_context_split["model_payload"]
                request = build_runtime_invocation(
                    node=node,
                    task=task,
                    task_type=schedule.get("task_type"),
                    model_tier=current_tier,
                    dependency_handoffs=dependency_handoffs,
                    context_pack=model_lane_context,
                    lane_budget=lane,
                    run_id=run_id,
                )
                if role in {"grader", "integrator"}:
                    request["synthesis_packet"] = synthesis_for_role
                    request["dependency_context_mode"] = "status-only+synthesis-packet"
                    request["repository_context_mode"] = "source-targeted-verification" if role == "grader" else "synthesis-only"
                    if verification_context_metrics is not None:
                        request["verification_context_metrics"] = verification_context_metrics
                request["attempt"] = attempt
                if lane_context is not None:
                    request["lane_context_budget"] = lane_context.get("budget")
                request["estimated_input_tokens"] = count_tokens(request, tokenizer=tokenizer, model=tokenizer_model)
                request["lane_budget_overflow"] = bool(lane_context and lane_context.get("budget", {}).get("overflow"))
                last_request = request
                result = adapter.invoke(request, root=root, cancellation=cancellation)
                usage = normalize_usage(result, request=request, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
                with state_lock:
                    consumed_input_tokens += int(usage.get("input_tokens", 0))
                    consumed_output_tokens += int(usage.get("output_tokens", 0))
                    if consumed_input_tokens >= int(context_tokens) and "context_tokens" not in budget_exhausted:
                        budget_exhausted.append("context_tokens")
                    if consumed_output_tokens >= int(output_tokens) and "output_tokens" not in budget_exhausted:
                        budget_exhausted.append("output_tokens")
                    if consumed_input_tokens > int(context_tokens) and "context_tokens" not in budget_overshoot:
                        budget_overshoot.append("context_tokens")
                    if consumed_output_tokens > int(output_tokens) and "output_tokens" not in budget_overshoot:
                        budget_overshoot.append("output_tokens")
                normalized = {**result, "usage_normalized": usage, "node_id": node_id, "role": role, "model_tier": current_tier, "attempt": attempt}
                lane_exceeded = []
                lane_output_limit = int(lane.get("output_tokens", 0))
                # lane.context_tokens budgets the sliced repository context only. Dependency
                # handoffs, synthesis metadata and runtime framing are governed by the
                # task-wide input-token budget and must not create a false lane overflow.
                if lane_context is not None and lane_context.get("budget", {}).get("overflow"):
                    lane_exceeded.append("context_tokens")
                if lane_output_limit >= 0 and int(usage.get("output_tokens", 0)) > lane_output_limit:
                    lane_exceeded.append("output_tokens")
                normalized["lane_budget_exceeded"] = lane_exceeded
                if lane_exceeded and bool(runtime_config.get("enforce_lane_budgets", True)) and normalized.get("status") == "success":
                    normalized["status"] = "budget-exceeded"
                    normalized["reason"] = "lane-budget-exceeded"
                    cancellation.cancel()
                attempts.append({"attempt": attempt, "status": normalized.get("status"), "model_tier": current_tier, "usage": usage, "lane_budget_exceeded": lane_exceeded})
                telemetry.record({"kind": "worker", "node_id": node_id, "role": role, "attempt": attempt, "status": normalized.get("status"), "usage": usage})
                trace.event("runtime-worker", {"node_id": node_id, "role": role, "attempt": attempt, "status": normalized.get("status"), "usage": usage})
                last_result = normalized
                if normalized.get("status") == "success":
                    break
                if normalized.get("status") in {"blocked", "cancelled"}:
                    break
                if attempt < max_attempts:
                    same_tier_retries = int(retry_cfg.get("same_tier_retries", 0))
                    if attempt > same_tier_retries:
                        current_tier = stronger(current_tier)
            last_result = {**last_result, "attempts": attempts, "attempt_count": len(attempts)}
            if budget_overshoot:
                cancellation.cancel()
            return node_id, last_result, last_request
        finally:
            with state_lock:
                active_workers -= 1

    for wave_index, wave in enumerate(schedule.get("waves", []), 1):
        if cancellation.cancelled or time.monotonic() >= deadline:
            cancellation.cancel()
            break
        runnable: list[str] = []
        skipped: list[dict[str, Any]] = []
        for node_id in wave:
            node = node_map[node_id]
            if results.get(node_id, {}).get("status") == "success":
                skipped.append({"status": "success", "reason": "resumed-success", "node_id": node_id, "role": node.get("role")})
                continue
            failed_deps = [dep for dep in node.get("depends_on", []) if results.get(dep, {}).get("status") != "success"]
            if failed_deps:
                item = {"status": "skipped", "reason": "dependency-not-successful", "failed_dependencies": failed_deps, "node_id": node_id, "role": node.get("role")}
                results[node_id] = item; skipped.append(item)
            else:
                runnable.append(node_id)
        wave_record = {"wave": wave_index, "nodes": list(wave), "runnable": runnable, "skipped": [x["node_id"] for x in skipped]}
        execution_waves.append(wave_record)
        if not runnable:
            continue
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=min(max_concurrency, len(runnable)), thread_name_prefix="repo-context-worker")
        futures = {pool.submit(invoke_node, node_id): node_id for node_id in runnable}
        pending = set(futures)

        def accept_future(future: concurrent.futures.Future[Any]) -> None:
            node_id = futures[future]
            try:
                _, result, _request = future.result()
            except concurrent.futures.CancelledError:
                result = {"status": "cancelled", "reason": "future-cancelled", "node_id": node_id, "role": node_map[node_id].get("role")}
            except Exception as exc:
                result = {"status": "failed", "reason": "runtime-engine-exception", "error": f"{type(exc).__name__}: {exc}", "node_id": node_id, "role": node_map[node_id].get("role")}
            results[node_id] = result
            if result.get("status") == "success":
                payload = result.get("payload")
                if node_map[node_id].get("role") == "grader" and bool(runtime_config.get("enforce_quality_gate", True)):
                    grade_payload = payload if isinstance(payload, dict) else {}
                    grade = evaluate_grade(grade_payload, risk_level=str(plan.get("risk", {}).get("level") or "medium"))
                    result["quality_gate"] = grade
                    if grade["decision"] != "pass":
                        result["status"] = "quality-gate-failed"
                        result["reason"] = f"grader-{grade['decision']}"
                        cancellation.cancel()
                handoffs[node_id] = reduce_handoff(
                    payload,
                    from_role=str(node_map[node_id].get("role") or "worker"),
                    to_role="dependent-stage",
                    task=task,
                    token_budget=int(runtime_config.get("handoff_token_budget", 1800)),
                    tokenizer=tokenizer,
                    tokenizer_model=tokenizer_model,
                )
                if node_map[node_id].get("role") not in {"grader", "integrator"}:
                    worker_outputs[node_id] = _checkpoint_worker_output(_worker_finding_envelope(node_map[node_id], payload))
            elif fail_fast and result.get("status") in {"failed", "timeout", "blocked", "budget-exceeded"}:
                cancellation.cancel()
            persist_checkpoint("running")

        try:
            while pending:
                done, pending = concurrent.futures.wait(pending, timeout=0.05, return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    accept_future(future)
                if time.monotonic() >= deadline and not cancellation.cancelled:
                    if "wall_seconds" not in budget_exhausted:
                        budget_exhausted.append("wall_seconds")
                    cancellation.cancel()
                if cancellation.cancelled and pending:
                    for future in pending:
                        future.cancel()
                    grace = max(0.0, float(runtime_config.get("cancellation_grace_seconds", 2.0)))
                    done_after_cancel, still_pending = concurrent.futures.wait(pending, timeout=grace)
                    for future in done_after_cancel:
                        accept_future(future)
                    pending = set(still_pending)
                    break
        finally:
            for future in pending:
                future.cancel()
            pool.shutdown(wait=not bool(pending), cancel_futures=True)
        if pending:
            for future in pending:
                node_id = futures[future]
                results.setdefault(node_id, {"status": "cancelled", "reason": "cancellation-grace-expired", "node_id": node_id, "role": node_map[node_id].get("role")})
        persist_checkpoint("cancelled" if cancellation.cancelled else "running")
        if cancellation.cancelled:
            break

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    elapsed_total_ms = round(previous_elapsed_ms + elapsed_ms, 2)
    pending = [node_id for node_id in node_map if node_id not in results]
    for node_id in pending:
        results[node_id] = {"status": "cancelled" if cancellation.cancelled else "skipped", "reason": "runtime-stopped-before-node", "node_id": node_id, "role": node_map[node_id].get("role")}

    successful_worker_outputs = list(worker_outputs.values())
    reduction = reduce_worker_outputs(successful_worker_outputs, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
    filter_audit = audit_filter_reduction(reduction)
    synthesis_packet = build_synthesis_packet(reduction, max_estimated_tokens=max(1, int(synthesis_budget)), tokenizer=tokenizer, tokenizer_model=tokenizer_model)
    synthesis_packet["filter_audit"] = filter_audit
    model_packet_split = split_model_packet(synthesis_packet, tokenizer=tokenizer, tokenizer_model=tokenizer_model)

    integrator_payload = None
    for node_id, node in node_map.items():
        if node.get("role") == "integrator" and results.get(node_id, {}).get("status") == "success":
            integrator_payload = results[node_id].get("payload")
    if integrator_payload is None:
        preferred_roles = ("worker", "implementer", "reviewer", "tester", "researcher", "planner")
        for wanted in preferred_roles:
            candidates = [node_id for node_id, node in node_map.items() if node.get("role") == wanted and results.get(node_id, {}).get("status") == "success"]
            if candidates:
                integrator_payload = results[candidates[-1]].get("payload")
                break

    final_evaluation = evaluate_final_answer(integrator_payload, final_answer_case) if final_answer_case is not None and integrator_payload is not None else None
    telemetry_summary = telemetry.summary()
    baseline_context_split = split_model_context(context_pack, tokenizer=tokenizer, tokenizer_model=tokenizer_model)
    baseline_input_tokens = count_tokens({"task": task, "context_pack": baseline_context_split["model_payload"]}, tokenizer=tokenizer, model=tokenizer_model)
    baseline_output_tokens = count_tokens(integrator_payload, tokenizer=tokenizer, model=tokenizer_model) if integrator_payload is not None else 0
    token_economics = summarize_token_economics(
        aggregate_input_tokens=int(telemetry_summary.get("input_tokens", 0)),
        aggregate_output_tokens=int(telemetry_summary.get("output_tokens", 0)),
        baseline_input_tokens=baseline_input_tokens,
        baseline_output_tokens=baseline_output_tokens,
        data_plane_input_tokens=int(telemetry_summary.get("data_plane_input_tokens_estimated", 0)),
        control_plane_input_tokens=int(telemetry_summary.get("control_plane_input_tokens_estimated", 0)),
        baseline_tokens_source="estimated",
        pipeline_input_tokens_source=str(telemetry_summary.get("input_tokens_source") or "estimated"),
        pipeline_output_tokens_source=str(telemetry_summary.get("output_tokens_source") or "estimated"),
        tokenizer=tokenizer,
        tokenizer_exact=bool(get_tokenizer(tokenizer, model=tokenizer_model).exact),
    )
    valid_count = max(1, int(reduction.get("stats", {}).get("valid_finding_count", 0) or 0))
    duplicate_ratio = min(1.0, int(reduction.get("stats", {}).get("duplicate_count", 0) or 0) / valid_count)
    contradiction_ratio = min(1.0, int(reduction.get("stats", {}).get("contradiction_count", 0) or 0) / max(1, int(reduction.get("stats", {}).get("output_finding_count", 0) or 0)))
    adaptive_reduction = choose_reduction_mode(
        task, source_tokens=baseline_input_tokens, duplicate_ratio=duplicate_ratio, conflict_ratio=contradiction_ratio,
        task_type=schedule.get("task_type"), complexity=plan.get("complexity"), risk=plan.get("risk"),
        requires_parallel_evidence=bool(plan.get("complexity", {}).get("multi_agent_recommended")),
    )
    status_counts = {status: sum(1 for r in results.values() if r.get("status") == status) for status in sorted({str(r.get("status")) for r in results.values()})}
    terminal_failures = {"failed", "timeout", "blocked", "cancelled", "quality-gate-failed", "budget-exceeded"}
    success = not any(r.get("status") in terminal_failures for r in results.values()) and not budget_overshoot and bool(filter_audit.get("passed"))
    runtime_result = {
        "schema": "repo-context-runtime-result/v1",
        "run_id": run_id,
        "task": task,
        "adapter": adapter_id,
        "success": success,
        "cancelled": cancellation.cancelled,
        "elapsed_ms": elapsed_ms,
        "elapsed_ms_total": elapsed_total_ms,
        "resumed": resume,
        "resume_count": resume_count,
        "plan": plan,
        "execution_waves": execution_waves,
        "nodes": results,
        "handoffs": handoffs,
        "fan_in": reduction,
        "filter_audit": filter_audit,
        "synthesis_packet": synthesis_packet,
        "model_packet": model_packet_split["model_payload"],
        "model_packet_metrics": model_packet_split["metrics"],
        "model_context_metrics": baseline_context_split["metrics"],
        "token_economics": token_economics,
        "adaptive_reduction": adaptive_reduction,
        "final_payload": integrator_payload,
        "final_answer_evaluation": final_evaluation,
        "telemetry": telemetry_summary,
        "status_counts": status_counts,
        "backpressure": {
            "max_concurrency": max_concurrency,
            "peak_active_workers": peak_active_workers,
            "model_calls_used": model_call_count,
            "model_calls_limit": int(model_calls),
            "input_tokens_used": consumed_input_tokens,
            "input_tokens_limit": int(context_tokens),
            "output_tokens_used": consumed_output_tokens,
            "output_tokens_limit": int(output_tokens),
            "budget_exhausted": list(budget_exhausted),
            "budget_overshoot": list(budget_overshoot),
        },
        "policy": {
            "fail_fast": fail_fast,
            "max_concurrency": max_concurrency,
            "wall_seconds": runtime_wall_seconds,
            "external_runtime_authorized": authorize_external,
            "runtime_network_authorized": authorize_network,
            "repository_write_authorized": authorize_write,
            "checkpoint_enabled": checkpoint_enabled,
            "repository_drift_allowed": allow_repo_drift,
            "cost_inference": False,
            "filter_invariant_gate": True,
            "model_packet_control_plane_separated": True,
            "adaptive_reduction_enforcement": "enforced" if effective_reduction_mode != "compat" else "compatibility-schedule",
        },
    }
    runtime_result["checkpoint"] = {"enabled": checkpoint_enabled, "path": str(store.path) if checkpoint_enabled else None}
    persist_checkpoint(
        "completed" if success else "cancelled" if cancellation.cancelled else "failed",
        final_summary={"success": success, "status_counts": status_counts, "final_answer_evaluation": final_evaluation, "filter_audit": filter_audit},
    )
    trace.event("runtime-finish", {"success": success, "cancelled": cancellation.cancelled, "elapsed_ms": elapsed_ms, "elapsed_ms_total": elapsed_total_ms, "status_counts": status_counts, "telemetry": telemetry_summary})
    return runtime_result
