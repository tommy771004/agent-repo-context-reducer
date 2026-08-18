from __future__ import annotations

import pathlib
import subprocess
from typing import Any

from .git_utils import git_root


def _run(root: pathlib.Path, args: list[str]) -> subprocess.CompletedProcess[bytes] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _text(cp: subprocess.CompletedProcess[bytes] | None) -> str | None:
    if cp is None or cp.returncode != 0:
        return None
    return cp.stdout.decode("utf-8", errors="replace").strip()


def repository_provenance(root: pathlib.Path | str) -> dict[str, Any]:
    requested = pathlib.Path(root).resolve()
    gr = git_root(requested)
    if gr is None:
        return {
            "classification": "repository-provenance",
            "git_available": False,
            "root": str(requested),
            "commit": None,
            "dirty": None,
        }
    commit = _text(_run(gr, ["rev-parse", "HEAD"]))
    branch = _text(_run(gr, ["branch", "--show-current"]))
    status = _run(gr, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    dirty = None if status is None or status.returncode != 0 else bool(status.stdout)
    try:
        subpath = requested.relative_to(gr).as_posix()
    except ValueError:
        subpath = "."
    return {
        "classification": "repository-provenance",
        "git_available": True,
        "root": str(requested),
        "git_root": str(gr),
        "repository_subpath": subpath,
        "commit": commit,
        "branch": branch or None,
        "dirty": dirty,
        "identity_rule": "commit + path + blob SHA; dirty working-tree content uses working_blob_sha",
    }


def _repo_relative(requested_root: pathlib.Path, rel: str, gr: pathlib.Path) -> str | None:
    path = (requested_root / rel).resolve()
    try:
        return path.relative_to(gr).as_posix()
    except ValueError:
        return None


def file_provenance(root: pathlib.Path | str, rel: str) -> dict[str, Any]:
    requested = pathlib.Path(root).resolve()
    gr = git_root(requested)
    normalized = pathlib.PurePosixPath(rel).as_posix().lstrip("./")
    if gr is None:
        return {
            "classification": "git-file-provenance",
            "path": normalized,
            "git_available": False,
            "tracked": False,
        }
    repo_rel = _repo_relative(requested, normalized, gr)
    path = (requested / normalized).resolve()
    if repo_rel is None or not path.exists() or not path.is_file():
        return {
            "classification": "git-file-provenance",
            "path": normalized,
            "git_available": True,
            "tracked": False,
            "error": "path unavailable or outside git root",
        }

    head_commit = _text(_run(gr, ["rev-parse", "HEAD"]))
    tracked_cp = _run(gr, ["ls-files", "--error-unmatch", "--", repo_rel])
    tracked = bool(tracked_cp is not None and tracked_cp.returncode == 0)
    head_blob = _text(_run(gr, ["rev-parse", f"HEAD:{repo_rel}"])) if tracked and head_commit else None

    index_blob = None
    if tracked:
        index_line = _text(_run(gr, ["ls-files", "-s", "--", repo_rel]))
        if index_line:
            parts = index_line.split()
            if len(parts) >= 2:
                index_blob = parts[1]

    working_blob = _text(_run(gr, ["hash-object", "--", repo_rel]))
    status_text = _text(_run(gr, ["status", "--porcelain=v1", "--untracked-files=all", "--", repo_rel]))
    dirty = bool(status_text)
    status_code = status_text[:2] if status_text else "  "

    return {
        "classification": "git-file-provenance",
        "path": normalized,
        "repo_path": repo_rel,
        "git_available": True,
        "tracked": tracked,
        "commit": head_commit,
        "head_blob_sha": head_blob,
        "index_blob_sha": index_blob,
        "working_blob_sha": working_blob,
        "dirty": dirty,
        "status": status_code,
        "content_identity": {
            "commit": head_commit,
            "path": repo_rel,
            "blob_sha": working_blob if dirty or not head_blob else head_blob,
            "source": "working-tree" if dirty or not head_blob else "HEAD",
        },
    }


def symbol_provenance(root: pathlib.Path | str, rel: str, symbol: str, *,
                      start_line: int | None = None, end_line: int | None = None,
                      fingerprint: str | None = None) -> dict[str, Any]:
    file_meta = file_provenance(root, rel)
    return {
        **file_meta,
        "classification": "git-symbol-provenance",
        "symbol": symbol,
        "start_line": start_line,
        "end_line": end_line,
        "symbol_fingerprint": fingerprint,
    }
