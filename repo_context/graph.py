from __future__ import annotations

import pathlib
from collections import defaultdict, deque
from typing import Any

from .util import SOURCE_EXTENSIONS


def _normalize_relative_spec(source: str, spec: str) -> str | None:
    base = pathlib.PurePosixPath(source).parent
    if spec.startswith("./") or spec.startswith("../") or spec.startswith("/"):
        raw = (base / spec).as_posix() if not spec.startswith("/") else spec.lstrip("/")
    elif spec.startswith("."):
        dots = len(spec) - len(spec.lstrip("."))
        rest = spec[dots:].replace(".", "/")
        parent = base
        for _ in range(max(0, dots - 1)):
            parent = parent.parent
        raw = (parent / rest).as_posix()
    else:
        return None

    parts: list[str] = []
    for part in pathlib.PurePosixPath(raw).parts:
        if part in ("", "."):
            continue
        if part == "..":
            if parts: parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


def _candidate_paths(source: str, spec: str, known: set[str]) -> list[str]:
    normalized = _normalize_relative_spec(source, spec)
    if normalized is None:
        return []
    candidates = [normalized]
    if pathlib.PurePosixPath(normalized).suffix:
        return [c for c in candidates if c in known]
    for ext in SOURCE_EXTENSIONS:
        candidates.append(normalized + ext)
    for ext in SOURCE_EXTENSIONS:
        candidates.append(normalized.rstrip("/") + "/index" + ext)
    candidates.append(normalized.rstrip("/") + "/__init__.py")
    return [c for c in candidates if c in known]


def build_dependency_graph(files: list[dict[str, Any]]) -> dict[str, Any]:
    known = {f["path"] for f in files}
    edges: dict[str, set[str]] = {p: set() for p in known}
    unresolved: dict[str, list[str]] = defaultdict(list)
    external: dict[str, list[str]] = defaultdict(list)
    for f in files:
        src = f["path"]
        for spec in f.get("imports", []):
            matches = _candidate_paths(src, spec, known)
            if matches:
                edges[src].add(matches[0])
            elif spec.startswith((".", "/")):
                unresolved[src].append(spec)
            else:
                external[src].append(spec)
    reverse: dict[str, set[str]] = {p: set() for p in known}
    for src, deps in edges.items():
        for dep in deps:
            reverse.setdefault(dep, set()).add(src)

    degree = {
        p: {"out": len(edges.get(p, ())), "in": len(reverse.get(p, ()))}
        for p in known
    }
    return {
        "edges": {k: sorted(v) for k, v in edges.items() if v},
        "reverse": {k: sorted(v) for k, v in reverse.items() if v},
        "degree": degree,
        "unresolved": {k: v[:20] for k, v in unresolved.items() if v},
        "external": {k: v[:20] for k, v in external.items() if v},
    }


def distances_from_entries(graph: dict[str, Any], entries: list[str]) -> dict[str, int]:
    edges = graph.get("edges", {})
    dist: dict[str, int] = {}
    q = deque()
    for e in entries:
        dist[e] = 0
        q.append(e)
    while q:
        cur = q.popleft()
        for nxt in edges.get(cur, []):
            if nxt not in dist:
                dist[nxt] = dist[cur] + 1
                q.append(nxt)
    return dist


def neighborhood(graph: dict[str, Any], seeds: list[str], depth: int = 1) -> list[str]:
    edges = graph.get("edges", {})
    reverse = graph.get("reverse", {})
    seen = set(seeds)
    frontier = set(seeds)
    for _ in range(max(depth, 0)):
        nxt = set()
        for p in frontier:
            nxt.update(edges.get(p, []))
            nxt.update(reverse.get(p, []))
        nxt -= seen
        seen |= nxt
        frontier = nxt
        if not frontier:
            break
    return sorted(seen)
