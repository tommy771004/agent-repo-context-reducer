from __future__ import annotations
import json,pathlib,time
from typing import Any
INDEX_VERSION=1; STATE_IGNORE_PATTERNS=(".repo-context/",".repo-context-cache/")
def state_dir(root:pathlib.Path)->pathlib.Path: return root/".repo-context"
def ensure_state_ignored(root:pathlib.Path)->dict[str,Any]:
    root=root.resolve(); ignore=root/".gitignore"
    try:
        existing=ignore.read_text(encoding="utf-8") if ignore.exists() else ""; lines={line.strip() for line in existing.splitlines()}; missing=[p for p in STATE_IGNORE_PATTERNS if p not in lines and p.rstrip("/") not in lines]
        if not missing:return {"path":str(ignore),"changed":False,"added":[]}
        prefix="" if not existing or existing.endswith("\n") else "\n"; block=prefix+"# agent-repo-context-reducer runtime state\n"+"\n".join(missing)+"\n"; ignore.write_text(existing+block,encoding="utf-8"); return {"path":str(ignore),"changed":True,"added":missing}
    except OSError as exc:return {"path":str(ignore),"changed":False,"added":[],"warning":str(exc)}
def prepare_state_dir(root:pathlib.Path)->pathlib.Path: ensure_state_ignored(root); folder=state_dir(root); folder.mkdir(parents=True,exist_ok=True); return folder
def index_path(root:pathlib.Path)->pathlib.Path:return state_dir(root)/"index.json"
def load_index(root:pathlib.Path)->dict[str,Any]|None:
    try:
        data=json.loads(index_path(root).read_text(encoding="utf-8")); return data if data.get("index_version")==INDEX_VERSION else None
    except (OSError,json.JSONDecodeError): return None
def save_index(root:pathlib.Path,index:dict[str,Any])->pathlib.Path:
    folder=prepare_state_dir(root); out=dict(index); out["index_version"]=INDEX_VERSION; out["indexed_at"]=int(time.time()); path=folder/"index.json"; tmp=path.with_suffix(".tmp"); tmp.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":")),encoding="utf-8"); tmp.replace(path); return path
def remove_index(root:pathlib.Path)->None:
    try:index_path(root).unlink()
    except FileNotFoundError:pass
