from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from .attribution import analyze_context_usage
from .benchmark import benchmark_tasks, load_tasks
from .artifact_store import ArtifactStore
from .complexity import classify_complexity
from .command_facade import get_facade, list_facades
from .capabilities import detect_providers, doctor, resolve_capability
from .context_command import execute_context
from .index_runtime import index_kwargs, persistent_index
from .repository_commands import REPOSITORY_VIEW_COMMANDS, handle_repository_view
from .repository_runtime import inspect_file, symbol_with_ledger as _symbol_with_ledger
from .config import load_config, trust_provider, prefer_provider
from .delegate import delegate_capability
from .external_context import load_external_file
from .fanout import recommend_fanout
from .handoff import reduce_handoff
from .grader import build_grade_packet, evaluate_grade
from .host_adapters import install_host_commands, host_status
from .indexer import build_persistent, ensure_index, index_status
from .knowledge import build_knowledge_index, search_knowledge, knowledge_status
from .lifecycle import ContextLifecycle
from .orchestration import plan_harness
from .provider_health import ProviderHealth
from .retry_policy import decide_retry
from .router import route_task
from .scheduler import build_schedule
from .task_budget import BudgetLimits, TaskBudget
from .tool_policy import classify_command
from .trace import replay_summary


from .cli_parser import build_parser


def _budget_for(args: argparse.Namespace) -> TaskBudget:
    limits = BudgetLimits(context_tokens=args.limit_context, output_tokens=args.limit_output,
                          tool_calls=args.limit_tools, model_calls=args.limit_models,
                          subagents=args.limit_subagents, wall_seconds=args.limit_wall)
    return TaskBudget(pathlib.Path(args.path).resolve(), args.run_id, limits=limits)


def _load_user_payload(value: str) -> Any:
    p = pathlib.Path(value)
    if p.is_file():
        text = p.read_text(encoding="utf-8", errors="replace")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            spec = get_facade(args.facade)
            if spec.mode == "doctor":
                forwarded = ["doctor", args.repo]
            else:
                task = args.task.strip() or spec.default_task
                forwarded = ["context", args.repo, task, "--budget", str(args.budget or spec.default_budget), "--session", args.session]
                if spec.intent:
                    forwarded.extend(["--intent", spec.intent])
            if args.pretty:
                forwarded.append("--pretty")
            return main(forwarded)
        if args.command == "commands":
            result = {"commands": list_facades(), "human_interface": "Use /reducer-* in Claude Code after host-install; Codex gets named reducer-* skills."}
            print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, separators=None if args.pretty else (",", ":")))
            return 0
        if args.command == "host-install":
            result = install_host_commands(args.repo, args.host, scope=args.scope, dry_run=args.dry_run)
            print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, separators=None if args.pretty else (",", ":")))
            return 0
        if args.command == "host-status":
            result = host_status(args.repo, args.host, scope=args.scope)
            print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, separators=None if args.pretty else (",", ":")))
            return 0
        if args.command == "complexity":
            result = classify_complexity(args.task, args.intent)
        elif args.command == "plan":
            result = plan_harness(args.task, args.repo, forced_type=args.intent, context_tokens=args.context_budget, output_tokens=args.output_budget, model_calls=args.model_calls)
        elif args.command == "schedule":
            result = build_schedule(args.task, args.intent)
        elif args.command == "quality":
            if args.action == "packet":
                if args.input is None:
                    raise ValueError("quality packet requires TASK and INPUT")
                result = build_grade_packet(args.value, _load_user_payload(args.input), task_type=args.intent, artifact_id=args.artifact_id)
            else:
                if not args.risk_level:
                    raise ValueError("quality evaluate requires --risk-level")
                payload = _load_user_payload(args.value)
                if not isinstance(payload, dict):
                    raise ValueError("quality evaluate expects a JSON object or JSON file")
                result = evaluate_grade(payload, risk_level=args.risk_level)
        elif args.command == "retry-decision":
            result = decide_retry(decision=args.decision, attempt=args.attempt, worker_tier=args.worker_tier,
                                  risk_level=args.risk_level, complexity_level=args.complexity_level,
                                  force_escalation=args.force_escalation)
        elif args.command == "handoff":
            root = pathlib.Path(args.repo).resolve()
            payload = _load_user_payload(args.input)
            artifact_id = None
            if args.store_artifact:
                artifact_id = ArtifactStore(root).put(payload, kind="agent-output", producer=args.from_role)["id"]
            result = reduce_handoff(payload, from_role=args.from_role, to_role=args.to_role, task=args.task, artifact_id=artifact_id)
        elif args.command == "artifact":
            store = ArtifactStore(pathlib.Path(args.repo).resolve())
            if args.action == "put":
                if not args.value: raise ValueError("artifact put requires a file path, JSON value, or text value")
                result = store.put(_load_user_payload(args.value), kind=args.kind, producer=args.producer)
            elif args.action == "get":
                if not args.value: raise ValueError("artifact get requires an artifact id")
                result = store.view(args.value, include_payload=args.payload)
            else:
                result = {"artifacts": store.list(args.limit)}
        elif args.command == "knowledge":
            if args.action == "index":
                result = build_knowledge_index(args.repo)
            elif args.action == "status":
                result = knowledge_status(args.repo)
            else:
                if not args.query: raise ValueError("knowledge search requires a query")
                result = search_knowledge(args.repo, args.query, top_k=args.top_k, budget=args.budget)
        elif args.command == "inspect":
            result = inspect_file(args.path, args.max_file_bytes)
        elif args.command == "detect":
            result = detect_providers(args.path, required=args.capability, use_cache=not args.no_cache)
        elif args.command == "doctor":
            result = doctor(args.path)
        elif args.command == "resolve":
            result = resolve_capability(args.path, args.capability, allow_external_commands=args.allow_external_commands)
        elif args.command == "delegate":
            result = delegate_capability(args.path, args.capability, args.task, allow_external_commands=args.allow_external_commands, timeout_seconds=args.timeout)
        elif args.command == "provider-health":
            result = {"providers": ProviderHealth(pathlib.Path(args.path).resolve()).summary(args.provider)}
        elif args.command == "provider-trust":
            result = trust_provider(pathlib.Path(args.path).resolve(), args.provider_id, True)
        elif args.command == "provider-untrust":
            result = trust_provider(pathlib.Path(args.path).resolve(), args.provider_id, False)
        elif args.command == "provider-prefer":
            root = pathlib.Path(args.path).resolve()
            if args.provider_id not in set(load_config(root).get("trusted_providers", [])):
                raise ValueError("Preferred external provider must be trusted first")
            result = prefer_provider(root, args.capability, args.provider_id)
        elif args.command == "provider-config":
            result = load_config(pathlib.Path(args.path).resolve())
        elif args.command == "route":
            result = route_task(args.task, None if args.no_resolve else args.repo)
        elif args.command == "ingest":
            result = {"provider": args.provider, "blocks": load_external_file(pathlib.Path(args.json_file), args.provider)}
        elif args.command == "status":
            result = index_status(args.path)
        elif args.command == "index":
            built = build_persistent(args.path, **index_kwargs(args)); idx = built["index"]
            result = {"mode": built["mode"], "index_path": built["path"], **index_status(args.path), "stats": idx.get("stats", {})}
        elif args.command == "sync":
            synced = ensure_index(args.path, sync=True, **index_kwargs(args))
            result = {"mode": synced["mode"], "index_path": synced["path"], **index_status(args.path), "sync_stats": synced["index"].get("sync_stats", {})}
        elif args.command == "symbol":
            root = pathlib.Path(args.path).resolve(); result = _symbol_with_ledger(root, args.file, args.symbol, args.session, args.max_file_bytes)
        elif args.command == "tool-policy":
            result = classify_command(args.command_line)
        elif args.command == "fanout":
            result = recommend_fanout(args.coverage, args.unresolved, args.used_subagents, args.max_subagents, args.concurrency)
        elif args.command == "budget":
            b = _budget_for(args)
            if args.action == "consume":
                result = b.consume(context_tokens=args.context_tokens, output_tokens=args.output_tokens,
                                   tool_calls=args.tool_calls, model_calls=args.model_calls, subagents=args.subagents)
            else:
                b.save(); result = b.status()
        elif args.command == "lifecycle":
            life = ContextLifecycle(pathlib.Path(args.path).resolve(), args.session)
            if args.action == "evict": result = life.evict(args.max_hot_tokens)
            else: result = {"session": args.session, "tiers": life.classify(), "items": life.data["items"]}; life.save()
        elif args.command == "replay":
            result = replay_summary(pathlib.Path(args.path).resolve(), args.run_id)
        elif args.command == "benchmark":
            result = benchmark_tasks(pathlib.Path(args.path).resolve(), load_tasks(pathlib.Path(args.tasks_json)), args.budget)
        elif args.command == "analyze-context":
            context_pack = json.loads(pathlib.Path(args.context_json).read_text(encoding="utf-8"))
            answer = pathlib.Path(args.answer_file).read_text(encoding="utf-8", errors="replace")
            result = analyze_context_usage(context_pack, answer)
        elif args.command == "context":
            result = execute_context(args)
        elif args.command in REPOSITORY_VIEW_COMMANDS:
            result = handle_repository_view(args, persistent_index(args))
        else:
            raise ValueError(f"Unknown command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2 if getattr(args, "pretty", False) else None,
                         separators=None if getattr(args, "pretty", False) else (",", ":")))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
