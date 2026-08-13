from __future__ import annotations

import pathlib
import shlex
import shutil
import sys
from typing import Any

from .command_facade import FACADES, FacadeCommand


PORTABLE_PROJECT_RUNTIME = "repo-context"


def _global_runtime_command(project_root: pathlib.Path) -> str:
    """Resolve a machine-local runtime for global shortcuts.

    Global shortcuts are intentionally local to one machine, so an absolute
    interpreter/script path is acceptable as a fallback. Project shortcuts use
    PORTABLE_PROJECT_RUNTIME instead because they may be committed and shared.
    """
    exe = shutil.which("repo-context")
    if exe:
        return shlex.quote(exe)
    package_root = pathlib.Path(__file__).resolve().parents[1]
    script = package_root / "scripts" / "repo_context.py"
    if script.exists():
        return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    script = project_root / "scripts" / "repo_context.py"
    if script.exists():
        return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    return f"{shlex.quote(sys.executable)} -m repo_context.cli"


def _runtime_command(project_root: pathlib.Path, scope: str) -> str:
    if scope == "project":
        return PORTABLE_PROJECT_RUNTIME
    return _global_runtime_command(project_root)


def render_claude_command(spec: FacadeCommand, runtime: str) -> str:
    task = "$ARGUMENTS" if spec.mode == "context" else ""
    run = (
        f'{runtime} run {spec.name} "{task}" --repo . --pretty'
        if spec.mode == "context"
        else f"{runtime} run {spec.name} --repo . --pretty"
    )
    return f"""---\ndescription: {spec.description}\nargument-hint: <task>\n---\n\n# {spec.name}\n\nUse Agent Repo Context Reducer before broad repository exploration.\n\nRun:\n\n```bash\n{run}\n```\n\nRules:\n- Do not recursively read the repository before this command.\n- Reuse compatible trusted providers when available.\n- Use native indexing only for missing or failed capabilities.\n- Reason from the returned bounded context first.\n- Expand to full files only when the returned evidence is insufficient.\n"""


def render_codex_skill(spec: FacadeCommand, runtime: str) -> str:
    run = (
        f'{runtime} run {spec.name} "<user task>" --repo . --pretty'
        if spec.mode == "context"
        else f"{runtime} run {spec.name} --repo . --pretty"
    )
    return f"""---\nname: {spec.name}\ndescription: {spec.description}\n---\n\n# {spec.name}\n\nTreat the user's request associated with this skill invocation as `<user task>`.\nDo not preload the repository. Run the reducer facade first:\n\n```bash\n{run}\n```\n\nThen reason from the returned minimal context. Reuse compatible trusted providers first and let the reducer use native fallback only for missing capabilities. Read full source only when the bounded context is insufficient.\n"""


def _target(host: str, scope: str, repo_root: pathlib.Path) -> pathlib.Path:
    home = pathlib.Path.home()
    if host == "claude-code":
        return repo_root / ".claude" / "commands" if scope == "project" else home / ".claude" / "commands"
    if host == "codex":
        return repo_root / ".agents" / "skills" if scope == "project" else home / ".codex" / "skills"
    raise ValueError(f"Unsupported host: {host}")


def install_host_commands(
    repo: str | pathlib.Path,
    host: str,
    scope: str = "project",
    dry_run: bool = False,
) -> dict[str, Any]:
    root = pathlib.Path(repo).resolve()
    target = _target(host, scope, root)
    runtime = _runtime_command(root, scope)
    warnings: list[str] = []
    if scope == "project" and shutil.which("repo-context") is None:
        warnings.append(
            "Project shortcuts intentionally use portable `repo-context`. "
            "Install the CLI on each machine (for example with pip/pipx) before invoking committed shortcuts."
        )
    written: list[str] = []
    if not dry_run:
        target.mkdir(parents=True, exist_ok=True)
    for spec in FACADES.values():
        if host == "claude-code":
            path = target / f"{spec.name}.md"
            content = render_claude_command(spec, runtime)
        else:
            path = target / spec.name / "SKILL.md"
            content = render_codex_skill(spec, runtime)
        written.append(str(path))
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return {
        "host": host,
        "scope": scope,
        "target": str(target),
        "runtime": runtime,
        "portable": scope == "project",
        "warnings": warnings,
        "commands": list(FACADES),
        "written": written,
        "dry_run": dry_run,
        "invocation": (
            "/reducer-* commands"
            if host == "claude-code"
            else "named reducer-* skills; use @ mention only if the current Codex client exposes skills through @"
        ),
    }


def host_status(repo: str | pathlib.Path, host: str, scope: str = "project") -> dict[str, Any]:
    root = pathlib.Path(repo).resolve()
    target = _target(host, scope, root)
    items: list[dict[str, Any]] = []
    for spec in FACADES.values():
        path = target / f"{spec.name}.md" if host == "claude-code" else target / spec.name / "SKILL.md"
        items.append({"name": spec.name, "path": str(path), "installed": path.exists()})
    return {
        "host": host,
        "scope": scope,
        "target": str(target),
        "commands": items,
        "all_installed": all(i["installed"] for i in items),
    }
