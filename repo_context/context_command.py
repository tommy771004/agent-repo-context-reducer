from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from .context_planner import build_context
from .delegate import delegate_capability
from .external_context import load_external_file
from .index_runtime import persistent_index
from .orchestration import plan_harness
from .router import route_task
from .task_budget import BudgetLimits, TaskBudget
from .trace import Trace, new_run_id


_NATIVE_REPOSITORY_CAPABILITIES = {
    "repository.index",
    "repository.graph",
    "repository.symbols",
    "repository.imports",
    "repository.references",
    "repository.impact",
    "code.read-symbol",
}


def _external_blocks(specs: list[str]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for spec in specs:
        if ":" not in spec:
            raise ValueError("--external expects PROVIDER:JSON_FILE")
        provider, raw_path = spec.split(":", 1)
        blocks.extend(load_external_file(pathlib.Path(raw_path).expanduser(), provider))
    return blocks


def _empty_index(root: pathlib.Path) -> dict[str, Any]:
    return {
        "root": str(root),
        "files": [],
        "by_path": {},
        "graph": {"edges": {}, "reverse": {}, "degree": {}},
        "entry_points": [],
        "manifests": [],
        "languages": {},
        "framework_hints": [],
        "directories": [],
        "workspaces": [],
        "stats": {"files_scanned": 0},
        "listing_mode": "external-only",
    }


def _auto_delegate_trusted(
    root: pathlib.Path,
    route: dict[str, Any],
    task: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    blocks: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    native_needed = False
    seen_exec: set[tuple[str, str]] = set()

    for capability, resolution in (route.get("provider_resolution") or {}).items():
        selected = resolution.get("selected") or {}
        source_type = selected.get("source_type")
        if source_type == "native":
            native_needed = native_needed or capability in _NATIVE_REPOSITORY_CAPABILITIES
            continue
        if source_type == "cli":
            continue
        if not resolution.get("trusted_selected"):
            native_needed = native_needed or capability in _NATIVE_REPOSITORY_CAPABILITIES
            continue

        command_key = json.dumps(
            (selected.get("commands") or {}).get(capability),
            sort_keys=True,
            ensure_ascii=False,
        )
        dedup_key = (selected.get("id", ""), command_key)
        if dedup_key in seen_exec:
            continue
        seen_exec.add(dedup_key)

        delegated = delegate_capability(root, capability, task, allow_external_commands=False)
        attempts.append(
            {
                "capability": capability,
                "provider": selected.get("id"),
                "delegated": delegated.get("delegated"),
                "reason": delegated.get("reason"),
            }
        )
        if delegated.get("delegated"):
            blocks.extend(delegated.get("blocks", []))
        elif capability in _NATIVE_REPOSITORY_CAPABILITIES:
            native_needed = True

    return blocks, attempts, native_needed


def execute_context(args: argparse.Namespace) -> dict[str, Any]:
    root = pathlib.Path(args.path).resolve()
    run_id = args.run_id or new_run_id()
    trace = Trace(root, run_id)
    route = route_task(args.task, args.path, forced_type=args.intent)
    trace.event("route", route)

    manual_blocks = _external_blocks(args.external)
    auto_blocks, delegation_attempts, native_needed = _auto_delegate_trusted(root, route, args.task)
    blocks = manual_blocks + auto_blocks
    trace.event(
        "provider-delegation",
        {
            "attempts": delegation_attempts,
            "manual_blocks": len(manual_blocks),
            "auto_blocks": len(auto_blocks),
        },
    )

    if args.external_only:
        if not blocks:
            raise ValueError("--external-only requires --external data or a trusted provider that successfully delegates")
        index = _empty_index(root)
        native_index_used = False
    elif not native_needed and blocks:
        index = _empty_index(root)
        native_index_used = False
    else:
        index = persistent_index(args)
        native_index_used = True

    result = build_context(
        index,
        args.task,
        budget=args.budget,
        session=args.session,
        max_files=args.max_context_files,
        max_symbols=args.max_symbols,
        include_content=not args.structure_only,
        external_blocks=blocks,
    )
    result["route"] = route
    result["run_id"] = run_id
    result["orchestration"] = plan_harness(
        args.task,
        root,
        forced_type=args.intent,
        context_tokens=max(args.budget, 800),
        output_tokens=4000,
        model_calls=10,
        route_result=route,
    )
    result["orchestration"]["execution"] = "advisory-only; this command does not spawn agents"
    result["provider_delegation"] = {
        "attempts": delegation_attempts,
        "manual_external_blocks": len(manual_blocks),
        "auto_external_blocks": len(auto_blocks),
        "native_index_used": native_index_used,
    }

    task_budget = TaskBudget(root, run_id, BudgetLimits(context_tokens=max(args.budget, 800)))
    task_budget.configure_lanes(result["orchestration"]["lane_budget"]["lanes"])
    tool_calls = 1 + len(delegation_attempts) + (1 if result.get("external_search", {}).get("used") else 0)
    result["task_budget"] = task_budget.consume(
        context_tokens=result["budget"]["estimated_used_tokens"],
        tool_calls=tool_calls,
    )

    trace.event(
        "routing-policy",
        {
            "complexity": result["orchestration"]["complexity"],
            "risk": result["orchestration"]["risk"],
            "model_roles": result["orchestration"]["model_policy"]["roles"],
            "retry_policy": result["orchestration"]["retry_policy"],
        },
    )
    trace.event(
        "context-pack",
        {
            "estimated_tokens": result["budget"]["estimated_used_tokens"],
            "files": len(result["files"]),
            "symbols": len(result["symbols"]),
            "external_blocks": len(result["external_context"]),
            "native_index_used": native_index_used,
            "coverage": result["coverage"],
            "stop_condition": result["stop_condition"],
        },
    )
    return result
