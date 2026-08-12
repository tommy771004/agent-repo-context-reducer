from __future__ import annotations

import pathlib
import subprocess


def _run_git(root: pathlib.Path, args: list[str]) -> subprocess.CompletedProcess[bytes] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=False, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def git_root(path: pathlib.Path) -> pathlib.Path | None:
    cp = _run_git(path, ["rev-parse", "--show-toplevel"])
    if not cp or cp.returncode != 0:
        return None
    try:
        return pathlib.Path(cp.stdout.decode().strip()).resolve()
    except Exception:
        return None


def tracked_and_unignored_files(root: pathlib.Path) -> list[pathlib.Path] | None:
    """List files using Git so .gitignore is honored, including for a repo subtree."""
    root = root.resolve()
    gr = git_root(root)
    if gr is None:
        return None
    try:
        prefix = root.relative_to(gr).as_posix()
    except ValueError:
        return None
    cp = _run_git(gr, ["ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    if not cp or cp.returncode != 0:
        return None
    paths: list[pathlib.Path] = []
    wanted = "" if prefix == "." else prefix.rstrip("/") + "/"
    for raw in cp.stdout.split(b"\x00"):
        if not raw:
            continue
        repo_rel = raw.decode("utf-8", errors="replace")
        if wanted:
            if not repo_rel.startswith(wanted):
                continue
            local_rel = repo_rel[len(wanted):]
        else:
            local_rel = repo_rel
        p = root / local_rel
        if p.is_file() or p.is_symlink():
            paths.append(p)
    return sorted(paths)


def changed_files(root: pathlib.Path, base: str | None = None) -> list[str]:
    root = root.resolve()
    gr = git_root(root)
    if gr is None:
        return []
    try:
        prefix = root.relative_to(gr).as_posix()
    except ValueError:
        return []
    wanted = "" if prefix == "." else prefix.rstrip("/") + "/"

    names: set[str] = set()
    commands: list[list[str]] = []
    if base:
        commands.append(["diff", "--name-only", "-z", f"{base}...HEAD"])
    # Always include current working-tree, staged, and untracked changes.
    commands.extend([
        ["diff", "--name-only", "-z"],
        ["diff", "--name-only", "--cached", "-z"],
        ["ls-files", "--others", "--exclude-standard", "-z"],
    ])
    for cmd in commands:
        cp = _run_git(gr, cmd)
        if not cp or cp.returncode != 0:
            continue
        for raw in cp.stdout.split(b"\x00"):
            if not raw:
                continue
            repo_rel = raw.decode("utf-8", errors="replace")
            if wanted:
                if not repo_rel.startswith(wanted):
                    continue
                rel = repo_rel[len(wanted):]
            else:
                rel = repo_rel
            if (root / rel).exists():
                names.add(rel)
    return sorted(names)
