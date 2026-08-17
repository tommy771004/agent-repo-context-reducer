from __future__ import annotations
import json,pathlib,re
from typing import Any
def _expand_glob(root:pathlib.Path,pattern:str)->list[str]:
    pattern=pattern.strip().strip("'\"")
    if not pattern or pattern.startswith("!"):return []
    out=[]
    try:
        for p in root.glob(pattern):
            if p.is_dir():out.append(p.relative_to(root).as_posix())
    except (OSError,ValueError):pass
    return out
def detect_workspaces(root:pathlib.Path)->list[dict[str,Any]]:
    found={};package=root/"package.json"
    if package.is_file():
        try:
            data=json.loads(package.read_text(encoding="utf-8"));ws=data.get("workspaces",[]);patterns=ws.get("packages",[]) if isinstance(ws,dict) else ws
            if isinstance(patterns,list):
                for pat in patterns:
                    if isinstance(pat,str):
                        for rel in _expand_glob(root,pat):found[rel]={"path":rel,"kind":"javascript-workspace"}
        except (OSError,json.JSONDecodeError):pass
    pnpm=root/"pnpm-workspace.yaml"
    if pnpm.is_file():
        try:
            for line in pnpm.read_text(encoding="utf-8",errors="replace").splitlines():
                m=re.match(r"\s*-\s*['\"]?([^'\"#]+)",line)
                if m:
                    for rel in _expand_glob(root,m.group(1).strip()):found.setdefault(rel,{"path":rel,"kind":"pnpm-workspace"})
        except OSError:pass
    cargo=root/"Cargo.toml"
    if cargo.is_file():
        try:
            text=cargo.read_text(encoding="utf-8",errors="replace");m=re.search(r"\[workspace\][\s\S]*?members\s*=\s*\[(.*?)\]",text,re.S)
            if m:
                for pat in re.findall(r"['\"]([^'\"]+)['\"]",m.group(1)):
                    for rel in _expand_glob(root,pat):found.setdefault(rel,{"path":rel,"kind":"cargo-workspace"})
        except OSError:pass
    for base in ("apps","packages","services"):
        d=root/base
        if d.is_dir():
            for child in sorted(d.iterdir()):
                if child.is_dir():
                    rel=child.relative_to(root).as_posix();found.setdefault(rel,{"path":rel,"kind":"monorepo-module"})
    return [found[k] for k in sorted(found)]
