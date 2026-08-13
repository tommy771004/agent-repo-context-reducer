from __future__ import annotations

import argparse

from . import __version__
from .command_facade import FACADES

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
    sync = sub.add_parser("sync", help="Refresh the persistent index; source parsing is cache-aware, graph/ranking are rebuilt")
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
    context.add_argument("--intent", choices=["understand", "debug", "change-impact", "review"],
                         help="Force a workflow intent instead of heuristic task routing")

    run = sub.add_parser("run", help="Run a short reducer-* intent facade")
    run.add_argument("facade", choices=list(FACADES))
    run.add_argument("task", nargs="?", default="")
    run.add_argument("--repo", default=".")
    run.add_argument("--budget", type=int)
    run.add_argument("--session", default="default")
    run.add_argument("--pretty", action="store_true")

    commands = sub.add_parser("commands", help="List the short reducer-* command facades")
    commands.add_argument("--pretty", action="store_true")

    hinstall = sub.add_parser("host-install", help="Install reducer-* shortcuts for Claude Code or Codex")
    hinstall.add_argument("--host", required=True, choices=["claude-code", "codex"])
    hinstall.add_argument("--scope", choices=["project", "global"], default="project")
    hinstall.add_argument("--repo", default=".")
    hinstall.add_argument("--dry-run", action="store_true")
    hinstall.add_argument("--pretty", action="store_true")

    hstatus = sub.add_parser("host-status", help="Show installed reducer-* host shortcuts")
    hstatus.add_argument("--host", required=True, choices=["claude-code", "codex"])
    hstatus.add_argument("--scope", choices=["project", "global"], default="project")
    hstatus.add_argument("--repo", default=".")
    hstatus.add_argument("--pretty", action="store_true")

    huninstall = sub.add_parser("host-uninstall", help="Remove reducer-* shortcuts installed by host-install")
    huninstall.add_argument("--host", required=True, choices=["claude-code", "codex"])
    huninstall.add_argument("--scope", choices=["project", "global"], default="project")
    huninstall.add_argument("--repo", default=".")
    huninstall.add_argument("--yes", action="store_true", help="Apply the removal; without this the command is a dry run")
    huninstall.add_argument("--force", action="store_true", help="Also remove shortcuts that were edited after installation")
    huninstall.add_argument("--pretty", action="store_true")

    update = sub.add_parser("update", help="Refresh what this runtime owns: persistent index and installed reducer-* shortcuts")
    update.add_argument("--repo", default=".")
    update.add_argument("--target", choices=["all", "index", "shortcuts", "self"], default="all")
    update.add_argument("--host", action="append", choices=["claude-code", "codex"], default=[],
                        help="Limit shortcut refresh to one host (repeatable); default is every host")
    update.add_argument("--scope", action="append", choices=["project", "global"], default=[],
                        help="Shortcut scopes to refresh (repeatable); default is project")
    update.add_argument("--dry-run", action="store_true")
    update.add_argument("--max-files", type=int, default=10000)
    update.add_argument("--max-file-bytes", type=int, default=512_000)
    update.add_argument("--include-hidden", action="store_true")
    update.add_argument("--include-generated", action="store_true")
    update.add_argument("--no-cache", action="store_true")
    update.add_argument("--pretty", action="store_true")

    remove = sub.add_parser("remove", help="Remove runtime state, installed shortcuts or stored artifacts")
    remove.add_argument("--repo", default=".")
    remove.add_argument("--target", choices=["state", "shortcuts", "artifacts", "all"], default="state")
    remove.add_argument("--host", action="append", choices=["claude-code", "codex"], default=[])
    remove.add_argument("--scope", action="append", choices=["project", "global"], default=[])
    remove.add_argument("--yes", action="store_true", help="Apply the removal; without this the command is a dry run")
    remove.add_argument("--all", dest="include_preserved", action="store_true",
                        help="Also remove provider trust, provider manifests and artifacts")
    remove.add_argument("--force", action="store_true", help="Also remove shortcuts that were edited after installation")
    remove.add_argument("--pretty", action="store_true")

    complexity = sub.add_parser("complexity", help="Heuristically classify task complexity before deciding whether multi-agent work is justified")
    complexity.add_argument("task"); complexity.add_argument("--intent", choices=["understand", "debug", "change-impact", "review"]); complexity.add_argument("--pretty", action="store_true")

    plan = sub.add_parser("plan", help="Build a provider-aware harness plan without executing agents")
    plan.add_argument("task"); plan.add_argument("--repo", default="."); plan.add_argument("--intent", choices=["understand", "debug", "change-impact", "review"])
    plan.add_argument("--context-budget", type=int, default=12000); plan.add_argument("--output-budget", type=int, default=4000); plan.add_argument("--model-calls", type=int, default=10); plan.add_argument("--pretty", action="store_true")

    schedule = sub.add_parser("schedule", help="Build a dependency-aware agent schedule; independent stages only may run in parallel")
    schedule.add_argument("task"); schedule.add_argument("--intent", choices=["understand", "debug", "change-impact", "review"]); schedule.add_argument("--pretty", action="store_true")

    quality = sub.add_parser("quality", help="Advanced runtime API: build a reduced grader packet or validate a grader result")
    quality.add_argument("action", choices=["packet", "evaluate"]); quality.add_argument("value"); quality.add_argument("input", nargs="?")
    quality.add_argument("--intent", choices=["understand", "debug", "change-impact", "review"]); quality.add_argument("--artifact-id")
    quality.add_argument("--risk-level", choices=["low", "medium", "high", "critical"]); quality.add_argument("--pretty", action="store_true")

    retry = sub.add_parser("retry-decision", help="Advanced runtime API: apply the bounded reject/retry/escalation policy")
    retry.add_argument("decision", choices=["pass", "reject", "uncertain"]); retry.add_argument("--attempt", type=int, required=True)
    retry.add_argument("--worker-tier", choices=["cheap", "standard", "strong"], required=True)
    retry.add_argument("--risk-level", choices=["low", "medium", "high", "critical"], required=True)
    retry.add_argument("--complexity-level", choices=["trivial", "focused", "complex", "autonomous"], required=True)
    retry.add_argument("--force-escalation", action="store_true"); retry.add_argument("--pretty", action="store_true")

    handoff = sub.add_parser("handoff", help="Reduce one agent result into a bounded structured handoff for another agent")
    handoff.add_argument("from_role"); handoff.add_argument("to_role"); handoff.add_argument("input")
    handoff.add_argument("--repo", default="."); handoff.add_argument("--task", default=""); handoff.add_argument("--store-artifact", action="store_true"); handoff.add_argument("--pretty", action="store_true")

    artifact = sub.add_parser("artifact", help="Store large agent/tool outputs outside model context and retrieve compact metadata")
    artifact.add_argument("action", choices=["put", "get", "list", "remove"]); artifact.add_argument("value", nargs="?")
    artifact.add_argument("--repo", default="."); artifact.add_argument("--kind", default="agent-output"); artifact.add_argument("--producer", default="unknown")
    artifact.add_argument("--payload", action="store_true", help="Include full payload when reading an artifact"); artifact.add_argument("--limit", type=int, default=50); artifact.add_argument("--pretty", action="store_true")

    knowledge = sub.add_parser("knowledge", help="Local knowledge-memory fallback for docs/ADR text; external knowledge providers remain preferred when compatible")
    knowledge.add_argument("action", choices=["index", "search", "status"]); knowledge.add_argument("query", nargs="?")
    knowledge.add_argument("--repo", default="."); knowledge.add_argument("--top-k", type=int, default=8); knowledge.add_argument("--budget", type=int, default=1800); knowledge.add_argument("--pretty", action="store_true")

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

