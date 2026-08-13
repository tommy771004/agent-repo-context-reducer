"""`update` and `remove` for everything the packaging layer cannot reach.

`npx skills update|remove` manages the installed Skill package, and pip/pipx manages the
`repo-context` console command. Neither knows about the shortcuts `host-install` writes into
slash-command directories, nor about the `.repo-context/` state this runtime creates inside
every scanned repository. Those are what this module maintains.

Self-update is reported, never executed: this project has no third-party dependencies and
does not shell out to package managers.
"""

from __future__ import annotations

import pathlib
import shutil
from typing import Any

from .artifact_store import ArtifactStore
from .host_adapters import host_status, install_host_commands, uninstall_host_commands
from .indexer import ensure_index, index_status
from .storage import state_dir

HOSTS = ("claude-code", "codex")
SCOPES = ("project", "global")

# Everything the runtime can rebuild from the repository itself.
REGENERABLE_STATE = (
    "index.json",
    "cache",
    "sessions",
    "runs",
    "budgets",
    "lifecycle",
    "provider-health.json",
    "knowledge.json",
)

# User-authored configuration and user data. Never removed unless explicitly requested,
# because no amount of re-scanning can reproduce them.
#   config.json    - persisted provider trust and preferences (config.py)
#   providers.json - resolved provider registry (capabilities.py)
#   providers.d/   - hand-written provider manifests
#   artifacts/     - stored agent/tool outputs
PRESERVED_STATE = (
    "config.json",
    "providers.json",
    "providers.d",
    "artifacts",
)


def _entry(root: pathlib.Path, name: str) -> dict[str, Any] | None:
    path = state_dir(root) / name
    if not path.exists():
        return None
    if path.is_dir():
        files = [p for p in path.rglob("*") if p.is_file()]
        size = sum(p.stat().st_size for p in files)
        return {"name": name, "path": str(path), "kind": "directory", "files": len(files), "bytes": size}
    return {"name": name, "path": str(path), "kind": "file", "files": 1, "bytes": path.stat().st_size}


def state_inventory(repo: pathlib.Path | str) -> dict[str, Any]:
    root = pathlib.Path(repo).resolve()
    regenerable = [e for e in (_entry(root, n) for n in REGENERABLE_STATE) if e]
    preserved = [e for e in (_entry(root, n) for n in PRESERVED_STATE) if e]
    unknown = []
    folder = state_dir(root)
    if folder.exists():
        known = set(REGENERABLE_STATE) | set(PRESERVED_STATE)
        unknown = [_entry(root, p.name) for p in sorted(folder.iterdir()) if p.name not in known]
        unknown = [e for e in unknown if e]
    return {
        "root": str(root),
        "state_dir": str(folder),
        "exists": folder.exists(),
        "regenerable": regenerable,
        "preserved": preserved,
        "unrecognized": unknown,
        "regenerable_bytes": sum(e["bytes"] for e in regenerable),
        "preserved_bytes": sum(e["bytes"] for e in preserved),
    }


def _delete(path: pathlib.Path) -> str | None:
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError as exc:
        return str(exc)
    return None


def remove_state(repo: pathlib.Path | str, yes: bool = False, include_preserved: bool = False) -> dict[str, Any]:
    root = pathlib.Path(repo).resolve()
    inventory = state_inventory(root)
    targets = list(inventory["regenerable"])
    if include_preserved:
        targets += inventory["preserved"] + inventory["unrecognized"]

    removed: list[str] = []
    failures: list[dict[str, str]] = []
    if yes:
        for item in targets:
            error = _delete(pathlib.Path(item["path"]))
            if error:
                failures.append({"path": item["path"], "error": error})
            else:
                removed.append(item["path"])
        folder = state_dir(root)
        if folder.exists() and not any(folder.iterdir()):
            folder.rmdir()
    kept = [] if include_preserved else inventory["preserved"] + inventory["unrecognized"]
    return {
        "target": "state",
        "root": str(root),
        "dry_run": not yes,
        "planned": [{"path": t["path"], "bytes": t["bytes"]} for t in targets],
        "removed": removed,
        "failures": failures,
        "kept": [{"path": k["path"], "reason": "user configuration or data"} for k in kept],
        "note": (
            "Dry run: nothing was removed. Re-run with --yes to apply."
            if not yes else "Removal applied."
        ) + (
            " Provider trust, provider manifests and artifacts were kept; pass --all to remove them too."
            if kept else ""
        ),
    }


def remove_shortcuts(repo: pathlib.Path | str, hosts: tuple[str, ...] = HOSTS,
                     scopes: tuple[str, ...] = ("project",), yes: bool = False,
                     force: bool = False) -> dict[str, Any]:
    results = [
        uninstall_host_commands(repo, host, scope=scope, yes=yes, force=force)
        for host in hosts for scope in scopes
    ]
    return {
        "target": "shortcuts",
        "dry_run": not yes,
        "hosts": list(hosts),
        "scopes": list(scopes),
        "results": results,
        "note": "host-install writes slash-command files that the Skill package manager does not track.",
    }


def remove_artifacts(repo: pathlib.Path | str, yes: bool = False) -> dict[str, Any]:
    root = pathlib.Path(repo).resolve()
    store = ArtifactStore(root)
    items = store.list(limit=10_000)
    removed: list[str] = []
    if yes:
        for item in items:
            error = _delete(store.dir / f"{item['id']}.json")
            if not error:
                removed.append(item["id"])
    return {
        "target": "artifacts",
        "root": str(root),
        "dry_run": not yes,
        "planned": [{"id": i["id"], "producer": i.get("producer"), "bytes": i.get("bytes")} for i in items],
        "removed": removed,
        "note": "Dry run: nothing was removed. Re-run with --yes to apply." if not yes else "Removal applied.",
    }


def self_update_hint(repo: pathlib.Path | str) -> dict[str, Any]:
    """Report how to update the installed distribution. Never executes anything."""
    cli = shutil.which("repo-context")
    skill_installed = any(
        (pathlib.Path(p).expanduser() / "agent-repo-context-reducer").exists()
        for p in ("~/.claude/skills", "~/.agents/skills", "~/.cursor/skills", "~/.codex/skills",
                  ".claude/skills", ".agents/skills")
    )
    return {
        "target": "self",
        "executed": False,
        "reason": "This runtime never invokes package managers; it reports the command for you to run.",
        "cli_on_path": cli,
        "skill_package_detected": skill_installed,
        "commands": {
            "skill_package": "npx skills update agent-repo-context-reducer",
            "skill_package_remove": "npx skills remove agent-repo-context-reducer",
            "python_cli": "python3 -m pip install -U git+https://github.com/tommy771004/agent-repo-context-reducer.git",
            "python_cli_remove": "python3 -m pip uninstall agent-repo-context-reducer",
        },
        "after_updating": "Run `repo-context update --target shortcuts` so installed /reducer-* files match the new renderer.",
    }


def update_index(repo: pathlib.Path | str, **index_kwargs: Any) -> dict[str, Any]:
    root = pathlib.Path(repo).resolve()
    before = index_status(root)
    result = ensure_index(root, sync=True, **index_kwargs)
    return {
        "target": "index",
        "mode": result["mode"],
        "path": result["path"],
        "previously_indexed": before.get("indexed", False),
        "files": len(result["index"].get("files", [])),
        "sync_stats": result["index"].get("sync_stats", {}),
    }


def update_shortcuts(repo: pathlib.Path | str, hosts: tuple[str, ...] = HOSTS,
                     scopes: tuple[str, ...] = ("project",), dry_run: bool = False) -> dict[str, Any]:
    """Re-render shortcuts that are already installed. Never installs new ones."""
    results: list[dict[str, Any]] = []
    for host in hosts:
        for scope in scopes:
            status = host_status(repo, host, scope=scope)
            if not any(item["installed"] for item in status["commands"]):
                results.append({"host": host, "scope": scope, "action": "skipped",
                                "reason": "no shortcuts installed for this host/scope"})
                continue
            written = install_host_commands(repo, host, scope=scope, dry_run=dry_run)
            results.append({"host": host, "scope": scope, "action": "re-rendered",
                            "runtime": written["runtime"], "written": written["written"]})
    return {
        "target": "shortcuts",
        "dry_run": dry_run,
        "results": results,
        "note": "Only hosts/scopes that already had shortcuts installed are refreshed.",
    }
