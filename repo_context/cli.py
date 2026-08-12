from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from . import __version__
from .admission import evaluate_read
from .attribution import analyze_context_usage
from .benchmark import benchmark_tasks, load_tasks
from .capabilities import detect_providers, doctor, resolve_capability
from .context_planner import build_context
from .config import load_config, trust_provider, prefer_provider
from .delegate import delegate_capability
from .external_context import load_external_file, canonicalize_external
from .fanout import recommend_fanout
from .git_utils import changed_files
from .graph import neighborhood
from .indexer import build_persistent, ensure_index, index_status
from .ledger import SessionLedger
from .lifecycle import ContextLifecycle
from .parsers import summarize_source
from .provider_health import ProviderHealth
from .ranking import rank_files
from .router import route_task
from .scanner import changed_view, dependency_view, module_map, project_map
from .symbols import read_symbol
from .task_budget import BudgetLimits, TaskBudget
from .tool_policy import classify_command
from .trace import Trace, new_run_id, replay_summary
from .util import SOURCE_EXTENSIONS, estimate_tokens_from_bytes, safe_read_text, is_secret_path


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--max-files", type=int, default=10000)
    p.add_argument("--max-file-bytes", type=int, default=512_000)
    p.add_argument("--include-hidden", action="store_true")
    p.add_argument("--include-generated", action="store_true")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--no-sync", action="store_true", help="Use existing persistent index without refreshing it")
    p.add_argument("--pretty", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repo-context", description="Provider-aware repository context harness for AI coding agents.")
    parser.add_argument("--version", action="version", version=f"repo-context {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    index = sub.add_parser("index", help="Build/rebuild the native persistent repository graph index")
    _add_common(index)
    sync = sub.add_parser("sync", help="Incrementally refresh the native persistent index")
    _add_common(sync)
    status = sub.add_parser("status", help="Show native persistent index status")
    status.add_argument("path", nargs="?", default="."); status.add_argument("--pretty", action="store_true")

    detect = sub.add_parser("detect", help="Lazy-detect compatible Skills/CLIs and native fallbacks")
    detect.add_argument("path", nargs="?", default="."); detect.add_argument("--capability", action="append", default=[])
    detect.add_argument("--no-cache", action="store_true"); detect.add_argument("--pretty", action="store_true")
    doc = sub.add_parser("doctor", help="Detect capability overlap and provider conflicts")
    doc.add_argument("path", nargs="?", default="."); doc.add_argument("--pretty", action="store_true")
    resolve = sub.add_parser("resolve", help="Resolve one capability to a provider; native is fallback")
    resolve.add_argument("capability"); resolve.add_argument("path", nargs="?", default=".")
    resolve.add_argument("--allow-external-commands", action="store_true"); resolve.add_argument("--pretty", action="store_true")
    delegate = sub.add_parser("delegate", help="Invoke an explicitly authorized compatible provider adapter without a shell")
    delegate.add_argument("capability"); delegate.add_argument("task"); delegate.add_argument("path", nargs="?", default=".")
    delegate.add_argument("--allow-external-commands", action="store_true"); delegate.add_argument("--timeout", type=int, default=30); delegate.add_argument("--pretty", action="store_true")
    phealth = sub.add_parser("provider-health", help="Show observed provider success/latency health")
    phealth.add_argument("path", nargs="?", default="."); phealth.add_argument("--provider"); phealth.add_argument("--pretty", action="store_true")
    ptrust = sub.add_parser("provider-trust", help="Persist trust for a machine-invokable external provider")
    ptrust.add_argument("provider_id"); ptrust.add_argument("path", nargs="?", default="."); ptrust.add_argument("--pretty", action="store_true")
    puntrust = sub.add_parser("provider-untrust", help="Remove persisted trust for an external provider")
    puntrust.add_argument("provider_id"); puntrust.add_argument("path", nargs="?", default="."); puntrust.add_argument("--pretty", action="store_true")
    ppref = sub.add_parser("provider-prefer", help="Prefer one trusted provider for a capability")
    ppref.add_argument("capability"); ppref.add_argument("provider_id"); ppref.add_argument("path", nargs="?", default="."); ppref.add_argument("--pretty", action="store_true")
    pcfg = sub.add_parser("provider-config", help="Show provider trust/preferences")
    pcfg.add_argument("path", nargs="?", default="."); pcfg.add_argument("--pretty", action="store_true")

    route = sub.add_parser("route", help="Classify a task and return workflow, policies, and required capabilities")
    route.add_argument("task"); route.add_argument("--repo", default="."); route.add_argument("--no-resolve", action="store_true")
    route.add_argument("--pretty", action="store_true")

    context = sub.add_parser("context", help="Build a provider-aware, token-budgeted context pack")
    _add_common(context); context.add_argument("task"); context.add_argument("--budget", type=int, default=6000)
    context.add_argument("--session", default="default"); context.add_argument("--run-id")
    context.add_argument("--max-context-files", type=int, default=12); context.add_argument("--max-symbols", type=int, default=20)
    context.add_argument("--structure-only", action="store_true")
    context.add_argument("--external-only", action="store_true", help="Use ingested external provider blocks without building the native repo index")
    context.add_argument("--external", action="append", default=[], metavar="PROVIDER:JSON",
                         help="Ingest external provider JSON through the context gateway before reasoning")

    ingest = sub.add_parser("ingest", help="Normalize/deduplicate an external provider JSON result")
    ingest.add_argument("provider"); ingest.add_argument("json_file"); ingest.add_argument("--pretty", action="store_true")

    map_p = sub.add_parser("map", help="Emit a compact Top-K native project map")
    _add_common(map_p); map_p.add_argument("--top-k", type=int, default=25); map_p.add_argument("--query")
    scan = sub.add_parser("scan", help="Backward-compatible alias for map")
    _add_common(scan); scan.add_argument("--top-k", type=int, default=25); scan.add_argument("--query")
    query = sub.add_parser("query", help="Rank repository files for a task/query")
    _add_common(query); query.add_argument("query"); query.add_argument("--top-k", type=int, default=20)
    module = sub.add_parser("module", help="Emit structural context for one module/subtree")
    _add_common(module); module.add_argument("module"); module.add_argument("--top-k", type=int, default=30); module.add_argument("--query")
    deps = sub.add_parser("deps", help="Show resolved static imports/imported-by neighborhood for a file")
    _add_common(deps); deps.add_argument("file"); deps.add_argument("--depth", type=int, default=1)
    callers = sub.add_parser("callers", help="Show files that statically import a file; not a runtime call graph")
    _add_common(callers); callers.add_argument("file")
    impact = sub.add_parser("impact", help="Show static dependency-neighborhood impact for a file")
    _add_common(impact); impact.add_argument("file"); impact.add_argument("--depth", type=int, default=2); impact.add_argument("--top-k", type=int, default=40)
    changed = sub.add_parser("changed", help="Show changed files and static dependency-neighborhood impact")
    _add_common(changed); changed.add_argument("--base"); changed.add_argument("--depth", type=int, default=1); changed.add_argument("--top-k", type=int, default=40)

    symbol = sub.add_parser("symbol", help="Read one symbol instead of an entire source file")
    symbol.add_argument("path", help="Repository root"); symbol.add_argument("file"); symbol.add_argument("symbol")
    symbol.add_argument("--session", default="default"); symbol.add_argument("--max-file-bytes", type=int, default=2_000_000); symbol.add_argument("--pretty", action="store_true")
    admit = sub.add_parser("admit", help="Evaluate whether a full file read should be admitted by policy")
    _add_common(admit); admit.add_argument("file"); admit.add_argument("task"); admit.add_argument("--session", default="default"); admit.add_argument("--requested", choices=["full", "structure", "symbol"], default="full")
    inspect = sub.add_parser("inspect", help="Extract structural metadata from one source file")
    inspect.add_argument("path"); inspect.add_argument("--max-file-bytes", type=int, default=1_000_000); inspect.add_argument("--pretty", action="store_true")

    tool = sub.add_parser("tool-policy", help="Classify shell/tool risk before execution")
    tool.add_argument("command_line"); tool.add_argument("--pretty", action="store_true")
    fan = sub.add_parser("fanout", help="Recommend adaptive subagent fan-out/backpressure")
    fan.add_argument("--coverage", type=float); fan.add_argument("--unresolved", type=int, default=1)
    fan.add_argument("--used-subagents", type=int, default=0); fan.add_argument("--max-subagents", type=int, default=4)
    fan.add_argument("--concurrency", type=int, default=2); fan.add_argument("--pretty", action="store_true")

    budget = sub.add_parser("budget", help="Create, inspect, or consume a task-wide harness budget")
    budget.add_argument("action", choices=["init", "status", "consume"]); budget.add_argument("run_id"); budget.add_argument("path", nargs="?", default=".")
    budget.add_argument("--context-tokens", type=int, default=0); budget.add_argument("--output-tokens", type=int, default=0)
    budget.add_argument("--tool-calls", type=int, default=0); budget.add_argument("--model-calls", type=int, default=0); budget.add_argument("--subagents", type=int, default=0)
    budget.add_argument("--limit-context", type=int, default=12000); budget.add_argument("--limit-output", type=int, default=4000)
    budget.add_argument("--limit-tools", type=int, default=30); budget.add_argument("--limit-models", type=int, default=10)
    budget.add_argument("--limit-subagents", type=int, default=4); budget.add_argument("--limit-wall", type=int, default=900); budget.add_argument("--pretty", action="store_true")

    life = sub.add_parser("lifecycle", help="Inspect or demote context lifecycle tiers")
    life.add_argument("action", choices=["status", "evict"]); life.add_argument("path", nargs="?", default=".")
    life.add_argument("--session", default="default"); life.add_argument("--max-hot-tokens", type=int, default=6000); life.add_argument("--pretty", action="store_true")

    replay = sub.add_parser("replay", help="Read an observational run trace without re-executing tools")
    replay.add_argument("run_id"); replay.add_argument("path", nargs="?", default="."); replay.add_argument("--pretty", action="store_true")

    bench = sub.add_parser("benchmark", help="Measure context selection/token reduction; optional expected-path recall")
    bench.add_argument("tasks_json"); bench.add_argument("path", nargs="?", default="."); bench.add_argument("--budget", type=int, default=6000); bench.add_argument("--pretty", action="store_true")

    attr = sub.add_parser("analyze-context", help="Heuristically identify possibly unused context after an answer")
    attr.add_argument("context_json"); attr.add_argument("answer_file"); attr.add_argument("--pretty", action="store_true")
    return parser


def _index_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return dict(max_files=args.max_files, max_file_bytes=args.max_file_bytes,
                include_hidden=args.include_hidden, use_cache=not args.no_cache,
                include_generated=args.include_generated)


def _persistent(args: argparse.Namespace) -> dict[str, Any]:
    return ensure_index(args.path, sync=not args.no_sync, **_index_kwargs(args))["index"]


def inspect_file(path: str, max_bytes: int) -> dict[str, Any]:
    p = pathlib.Path(path).expanduser().absolute()
    if is_secret_path(p.as_posix()):
        raise ValueError(f"Refusing to inspect secret-like path: {p}")
    if not p.is_file():
        raise ValueError(f"Not a file: {p}")
    text, size, reason = safe_read_text(p, max_bytes)
    if text is None:
        raise ValueError(f"File unavailable ({reason}): {p}")
    summary = summarize_source(p.name, text)
    return {"path": str(p), "language": SOURCE_EXTENSIONS.get(p.suffix.lower()), "bytes": size,
            **summary, "estimated_raw_tokens": estimate_tokens_from_bytes(size)}


def _symbol_with_ledger(root: pathlib.Path, file: str, name: str, session: str, max_bytes: int) -> dict[str, Any]:
    item = read_symbol(root, file, name, max_file_bytes=max_bytes)
    ledger = SessionLedger(root, session=session)
    key = f"symbol:{item['path']}:{item['name']}:{item.get('start_line')}"
    comparison = ledger.compare(key, item["fingerprint"], item["content"])
    if comparison["state"] == "unchanged":
        result = {k: v for k, v in item.items() if k != "content"}
        result.update({"content_mode": "omitted-unchanged", "session": session, "already_seen": True})
    elif comparison["state"] == "changed" and comparison.get("diff") and len(comparison["diff"]) < len(item["content"]):
        result = {**item, "content": comparison["diff"], "content_mode": "delta", "session": session, "already_seen": False}
    else:
        result = {**item, "content_mode": "full-symbol", "session": session, "already_seen": False}
    ledger.record(key, item["fingerprint"], item["content"])
    ledger.save()
    return result


def _external_blocks(specs: list[str]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for spec in specs:
        if ":" not in spec:
            raise ValueError("--external expects PROVIDER:JSON_FILE")
        provider, raw_path = spec.split(":", 1)
        p = pathlib.Path(raw_path).expanduser()
        blocks.extend(load_external_file(p, provider))
    return blocks


def _budget_for(args: argparse.Namespace) -> TaskBudget:
    limits = BudgetLimits(context_tokens=args.limit_context, output_tokens=args.limit_output,
                          tool_calls=args.limit_tools, model_calls=args.limit_models,
                          subagents=args.limit_subagents, wall_seconds=args.limit_wall)
    return TaskBudget(pathlib.Path(args.path).resolve(), args.run_id, limits=limits)


def _empty_index(root: pathlib.Path) -> dict[str, Any]:
    return {
        "root": str(root), "files": [], "by_path": {},
        "graph": {"edges": {}, "reverse": {}, "degree": {}},
        "entry_points": [], "manifests": [], "languages": {}, "framework_hints": [],
        "directories": [], "workspaces": [], "stats": {"files_scanned": 0}, "listing_mode": "external-only",
    }


def _auto_delegate_trusted(root: pathlib.Path, route: dict[str, Any], task: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    blocks: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    native_needed = False
    native_repo_caps = {
        "repository.index", "repository.graph", "repository.symbols", "repository.imports",
        "repository.references", "repository.impact", "code.read-symbol"
    }
    seen_exec: set[tuple[str, str]] = set()
    for cap, resolution in (route.get("provider_resolution") or {}).items():
        selected = resolution.get("selected") or {}
        if selected.get("source_type") == "native":
            if cap in native_repo_caps:
                native_needed = True
            continue
        if selected.get("source_type") == "cli":
            continue
        if not resolution.get("trusted_selected"):
            if cap in native_repo_caps:
                native_needed = True
            continue
        command_key = json.dumps((selected.get("commands") or {}).get(cap), sort_keys=True, ensure_ascii=False)
        dedup_key = (selected.get("id", ""), command_key)
        if dedup_key in seen_exec:
            continue
        seen_exec.add(dedup_key)
        delegated = delegate_capability(root, cap, task, allow_external_commands=False)
        attempts.append({"capability": cap, "provider": selected.get("id"), "delegated": delegated.get("delegated"), "reason": delegated.get("reason")})
        if delegated.get("delegated"):
            blocks.extend(delegated.get("blocks", []))
        elif cap in native_repo_caps:
            native_needed = True
    return blocks, attempts, native_needed


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
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
            built = build_persistent(args.path, **_index_kwargs(args)); idx = built["index"]
            result = {"mode": built["mode"], "index_path": built["path"], **index_status(args.path), "stats": idx.get("stats", {})}
        elif args.command == "sync":
            synced = ensure_index(args.path, sync=True, **_index_kwargs(args))
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
        else:
            if args.command == "context":
                root = pathlib.Path(args.path).resolve()
                run_id = args.run_id or new_run_id()
                trace = Trace(root, run_id)
                route = route_task(args.task, args.path)
                trace.event("route", route)

                manual_blocks = _external_blocks(args.external)
                auto_blocks, delegation_attempts, native_needed = _auto_delegate_trusted(root, route, args.task)
                blocks = manual_blocks + auto_blocks
                trace.event("provider-delegation", {
                    "attempts": delegation_attempts,
                    "manual_blocks": len(manual_blocks),
                    "auto_blocks": len(auto_blocks),
                })

                if args.external_only:
                    if not blocks:
                        raise ValueError("--external-only requires --external data or a trusted provider that successfully delegates")
                    index = _empty_index(root)
                    native_index_used = False
                elif not native_needed and blocks:
                    index = _empty_index(root)
                    native_index_used = False
                else:
                    index = _persistent(args)
                    native_index_used = True

                result = build_context(index, args.task, budget=args.budget, session=args.session,
                                       max_files=args.max_context_files, max_symbols=args.max_symbols,
                                       include_content=not args.structure_only, external_blocks=blocks)
                result["route"] = route
                result["run_id"] = run_id
                result["provider_delegation"] = {
                    "attempts": delegation_attempts,
                    "manual_external_blocks": len(manual_blocks),
                    "auto_external_blocks": len(auto_blocks),
                    "native_index_used": native_index_used,
                }
                task_budget = TaskBudget(root, run_id, BudgetLimits(context_tokens=max(args.budget, 800)))
                tool_calls = 1 + len(delegation_attempts) + (1 if result.get("external_search", {}).get("used") else 0)
                budget_state = task_budget.consume(context_tokens=result["budget"]["estimated_used_tokens"], tool_calls=tool_calls)
                result["task_budget"] = budget_state
                trace.event("context-pack", {
                    "estimated_tokens": result["budget"]["estimated_used_tokens"],
                    "files": len(result["files"]), "symbols": len(result["symbols"]),
                    "external_blocks": len(result["external_context"]),
                    "native_index_used": native_index_used,
                    "coverage": result["coverage"], "stop_condition": result["stop_condition"],
                })
            else:
                index = _persistent(args)
                if args.command in {"map", "scan"}:
                    result = project_map(index, top_k=args.top_k, query=args.query)
                elif args.command == "query":
                    result = project_map(index, top_k=args.top_k, query=args.query)
                elif args.command == "module":
                    result = module_map(index, args.module, top_k=args.top_k, query=args.query)
                elif args.command == "deps":
                    result = dependency_view(index, args.file, depth=args.depth)
                    result["graph_semantics"] = "resolved static import graph; not a runtime call graph"
                elif args.command == "callers":
                    rel = pathlib.PurePosixPath(args.file).as_posix().lstrip("./")
                    if rel not in index["by_path"]:
                        raise ValueError(f"File not indexed: {rel}")
                    result = {"path": rel, "statically_imported_by": index["graph"].get("reverse", {}).get(rel, []),
                              "confidence": "high-for-resolved-static-imports", "not_provided": "runtime callers"}
                elif args.command == "impact":
                    rel = pathlib.PurePosixPath(args.file).as_posix().lstrip("./")
                    if rel not in index["by_path"]:
                        raise ValueError(f"File not indexed: {rel}")
                    affected = neighborhood(index["graph"], [rel], depth=args.depth)
                    ranked = rank_files([index["by_path"][p] for p in affected if p in index["by_path"]], index["graph"], index["entry_points"])
                    result = {"seed": rel, "depth": args.depth, "affected_files": [f["path"] for f in ranked[:args.top_k]],
                              "classification": "static-dependency-neighborhood", "runtime_impact_guarantee": False}
                elif args.command == "changed":
                    changed = changed_files(pathlib.Path(args.path).resolve(), base=args.base)
                    result = changed_view(index, changed, depth=args.depth, top_k=args.top_k)
                elif args.command == "admit":
                    result = evaluate_read(index, args.file, args.task, session=args.session, requested=args.requested)
                else:
                    raise ValueError(f"Unknown command: {args.command}")
        print(json.dumps(result, ensure_ascii=False, indent=2 if getattr(args, "pretty", False) else None,
                         separators=None if getattr(args, "pretty", False) else (",", ":")))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
