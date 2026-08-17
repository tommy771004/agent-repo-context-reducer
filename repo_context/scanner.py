from __future__ import annotations

import json
import os
import pathlib
from collections import Counter
from typing import Any

from .cache import SummaryCache
from .git_utils import tracked_and_unignored_files
from .graph import build_dependency_graph, neighborhood
from .parsers import summarize_source
from .ranking import rank_files
from .symbols import extract_symbol_index
from .util import (
    DEFAULT_IGNORE_DIRS, ENTRY_NAMES, SOURCE_EXTENSIONS, TEXT_CONFIG_EXTS,
    estimate_tokens_from_bytes, file_cache_key, is_generated_path, is_manifest,
    is_secret_path, json_bytes, looks_generated, safe_read_text,
)
from .workspaces import detect_workspaces


def detect_framework_hints(manifest_texts: dict[str, str]) -> list[str]:
    corpus = "\n".join(manifest_texts.values()).lower()
    patterns = {
        "React": ['"react"', "react-dom"], "Next.js": ['"next"'], "Vue": ['"vue"'],
        "Svelte": ['"svelte"'], "Express": ['"express"'], "NestJS": ["@nestjs/"],
        "Tauri": ["@tauri-apps", "tauri ="], "Django": ["django"], "FastAPI": ["fastapi"],
        "Flask": ["flask"], ".NET": ["microsoft.net.sdk", "<targetframework>"],
        "ASP.NET Core": ["microsoft.net.sdk.web", "aspnetcore"], "Spring": ["spring-boot", "org.springframework"],
        "Rails": ["rails"], "Laravel": ["laravel/framework"],
    }
    return [name for name, needles in patterns.items() if any(n in corpus for n in needles)]


def _is_entry_point(rel: str, name: str) -> bool:
    parts = pathlib.PurePosixPath(rel).parts
    if rel in {"main.py","app.py","manage.py","__main__.py","index.js","index.ts","index.tsx","main.js","main.ts","main.tsx","server.js","server.ts","Program.cs","main.rs","lib.rs","main.go","App.tsx","App.jsx"}:
        return True
    if len(parts)==2 and parts[0] in {"src","app"} and name in ENTRY_NAMES: return True
    if len(parts)==3 and parts[0]=="cmd" and name=="main.go": return True
    return False


def _static_importance(path: str, summary: dict[str, Any], manifest: bool, entry: bool) -> int:
    lower=path.lower(); score=25 if entry else 0; score += 12 if manifest else 0
    if any(x in lower for x in ("router","route","controller","service","main","index","app","server")): score += 5
    if any(x in lower for x in ("auth","security","payment","database","db","config")): score += 3
    score += min(len(summary.get("imports",[])),8) + min(len(summary.get("classes",[]))*2,8) + min(len(summary.get("routes",[]))*2,8)
    return score


def _walk_files(root: pathlib.Path, include_hidden: bool) -> list[pathlib.Path]:
    paths=[]
    for current,dirs,names in os.walk(root,followlinks=False):
        current_path=pathlib.Path(current)
        dirs[:] = [d for d in sorted(dirs) if d not in DEFAULT_IGNORE_DIRS and (include_hidden or not d.startswith(".")) and not (current_path/d).is_symlink()]
        for name in sorted(names):
            if not include_hidden and name.startswith("."): continue
            paths.append(current_path/name)
    return paths


def _candidate_files(root: pathlib.Path, include_hidden: bool) -> tuple[list[pathlib.Path], str]:
    git_files=tracked_and_unignored_files(root)
    return (git_files,"git-ls-files") if git_files is not None else (_walk_files(root,include_hidden),"filesystem-walk")


def _is_relevant(path: pathlib.Path) -> bool:
    return path.suffix.lower() in SOURCE_EXTENSIONS or is_manifest(path) or path.suffix.lower() in TEXT_CONFIG_EXTS or path.name in ENTRY_NAMES


def build_index(root: pathlib.Path | str, max_files: int=10000, max_file_bytes: int=512_000,
                include_hidden: bool=False, use_cache: bool=True, include_generated: bool=False) -> dict[str, Any]:
    root=pathlib.Path(root).resolve()
    if not root.exists() or not root.is_dir(): raise ValueError(f"Not a directory: {root}")
    candidate_paths,listing_mode=_candidate_files(root,include_hidden); cache=SummaryCache(root,enabled=use_cache)
    files=[]; manifests=[]; entries=[]; manifest_texts={}; language_counts=Counter(); directory_counts=Counter(); stats=Counter(); raw_bytes=0
    for path in candidate_paths:
        if len(files)>=max_files: stats["max_files_reached"]+=1; break
        try: rel=path.resolve(strict=False).relative_to(root).as_posix()
        except ValueError: stats["outside_root"]+=1; continue
        if rel.startswith((".repo-context/",".repo-context-cache/")): stats["internal_state_skipped"]+=1; continue
        if is_secret_path(rel): stats["secret_paths_skipped"]+=1; continue
        if not include_generated and is_generated_path(rel): stats["generated_paths_skipped"]+=1; continue
        if not _is_relevant(path): continue
        if path.is_symlink(): stats["symlinks_skipped"]+=1; continue
        try: size=path.stat().st_size
        except OSError: stats["unreadable_skipped"]+=1; continue
        raw_bytes+=size
        if size>max_file_bytes: stats["large_skipped"]+=1; continue
        ext=path.suffix.lower(); source=ext in SOURCE_EXTENSIONS; manifest=is_manifest(path); entry=_is_entry_point(rel,path.name)
        summary=None; key=""
        if source and use_cache:
            try: key=file_cache_key(path); summary=cache.get(rel,key)
            except OSError: key=""
        text=None
        if summary is None or manifest or not source:
            text,_,reason=safe_read_text(path,max_file_bytes)
            if text is None: stats[f"{reason or 'unreadable'}_skipped"]+=1; continue
            if not include_generated and looks_generated(text): stats["generated_content_skipped"]+=1; continue
        if manifest: manifests.append(rel); manifest_texts[rel]=(text or "")[:100_000]
        if entry: entries.append(rel)
        if source: language_counts[SOURCE_EXTENSIONS[ext]]+=1; stats["source_files"]+=1
        directory_counts[path.parent.relative_to(root).as_posix() or "."]+=1
        if summary is None:
            summary=summarize_source(rel,text or "") if source else {"imports":[],"classes":[],"types":[],"functions":[],"exports":[],"routes":[],"symbols":[],"symbol_details":[],"lines":len((text or "").splitlines()),"parser":"manifest/config"}
            if source: summary["symbol_details"]=extract_symbol_index(rel,text or ""); stats["cache_misses"]+=1
            if source and use_cache and key: cache.put(rel,key,summary)
        else: stats["cache_hits"]+=1
        try: stat_fingerprint=file_cache_key(path)
        except OSError: stat_fingerprint=""
        item={"path":rel,"language":SOURCE_EXTENSIONS.get(ext),"bytes":size,"stat_fingerprint":stat_fingerprint,"lines":summary["lines"],"imports":summary.get("imports",[]),"classes":summary.get("classes",[]),"types":summary.get("types",[]),"functions":summary.get("functions",[]),"exports":summary.get("exports",[]),"routes":summary.get("routes",[]),"symbols":summary.get("symbols",[]),"symbol_details":summary.get("symbol_details",[]),"parser":summary.get("parser"),"manifest":manifest,"entry_point":entry}
        item["static_importance"]=_static_importance(rel,item,manifest,entry); files.append(item)
    cache.save(); graph=build_dependency_graph(files); ranked=rank_files(files,graph,sorted(set(entries))); by_path={f["path"]:f for f in ranked}
    stats["files_scanned"]=len(files); stats["source_bytes_considered"]=raw_bytes
    return {"root":str(root),"listing_mode":listing_mode,"files":ranked,"by_path":by_path,"graph":graph,"entry_points":sorted(set(entries)),"manifests":sorted(set(manifests)),"languages":dict(language_counts.most_common()),"framework_hints":detect_framework_hints(manifest_texts),"directories":[{"path":p,"files":c} for p,c in directory_counts.most_common(60)],"workspaces":detect_workspaces(root),"stats":dict(stats)}


def compact_file(f: dict[str, Any]) -> dict[str, Any]:
    return {"path":f["path"],"language":f.get("language"),"lines":f.get("lines"),"imports":f.get("imports",[]),"classes":f.get("classes",[]),"types":f.get("types",[]),"functions":f.get("functions",[]),"exports":f.get("exports",[]),"routes":f.get("routes",[]),"rank_score":f.get("rank_score"),"rank_reasons":f.get("rank_reasons",[])}


def project_map(index: dict[str, Any], top_k:int=25, query:str|None=None) -> dict[str, Any]:
    ranked=index["files"] if not query else rank_files(index["files"],index["graph"],index["entry_points"],query=query)
    selected=[compact_file(f) for f in ranked[:max(1,top_k)]]; degree=index["graph"].get("degree",{}); central=sorted(degree.items(),key=lambda kv:(-(kv[1]["in"]+kv[1]["out"]),kv[0]))[:20]
    result={"project":{"root_name":pathlib.Path(index["root"]).name,"listing_mode":index["listing_mode"],"files_scanned":index["stats"].get("files_scanned",0),"languages":index["languages"],"framework_hints":index["framework_hints"],"manifests":index["manifests"],"workspaces":index["workspaces"]},"query":query,"entry_points":index["entry_points"],"directories":index["directories"][:30],"important_files":selected,"central_files":[{"path":p,**d} for p,d in central],"stats":{**{k:v for k,v in index["stats"].items() if k!="source_bytes_considered"},"source_bytes_considered":index["stats"].get("source_bytes_considered",0),"estimated_raw_tokens":estimate_tokens_from_bytes(index["stats"].get("source_bytes_considered",0)),"top_k":top_k,"output_note":"Default output includes only ranked Top-K structural summaries, not every file."}}
    out_bytes=json_bytes(result); result["stats"]["output_json_bytes"]=out_bytes; result["stats"]["estimated_output_tokens"]=estimate_tokens_from_bytes(out_bytes); raw=index["stats"].get("source_bytes_considered",0); result["stats"]["estimated_reduction_ratio"]=round(max(0.0,1-out_bytes/raw),4) if raw else 0.0; result["stats"]["token_estimate_note"]="UTF-8 bytes / 4 approximation; not a tokenizer or billing estimate."; return result


def query_view(index: dict[str, Any], query:str, top_k:int=20) -> dict[str, Any]:
    ranked=rank_files(index["files"],index["graph"],index["entry_points"],query=query); selected=[compact_file(f) for f in ranked[:max(1,top_k)]]
    result={"query":query,"mode":"task-ranked-query","matches":selected,"project":{"root_name":pathlib.Path(index["root"]).name,"files_scanned":index["stats"].get("files_scanned",0),"languages":index.get("languages",{})},"stats":{"top_k":top_k,"source_bytes_considered":index["stats"].get("source_bytes_considered",0),"output_note":"Task-specific ranking; this is distinct from the architecture-oriented project map."}}
    out_bytes=json_bytes(result); result["stats"]["output_json_bytes"]=out_bytes; result["stats"]["estimated_output_tokens"]=estimate_tokens_from_bytes(out_bytes); result["stats"]["token_estimate_note"]="UTF-8 bytes / 4 approximation; not a tokenizer or billing estimate."; return result


def module_map(index:dict[str,Any],module:str,top_k:int=30,query:str|None=None)->dict[str,Any]:
    prefix=module.strip("./"); subset=[f for f in index["files"] if f["path"]==prefix or f["path"].startswith(prefix.rstrip("/")+"/")]; ranked=subset if not query else rank_files(subset,index["graph"],[e for e in index["entry_points"] if e.startswith(prefix)],query=query); return {"module":prefix or ".","query":query,"files_found":len(subset),"important_files":[compact_file(f) for f in ranked[:max(1,top_k)]]}


def dependency_view(index:dict[str,Any],path:str,depth:int=1)->dict[str,Any]:
    rel=pathlib.PurePosixPath(path).as_posix().lstrip("./")
    if rel not in index["by_path"]: raise ValueError(f"File not indexed: {rel}")
    graph=index["graph"]; return {"path":rel,"imports":graph.get("edges",{}).get(rel,[]),"imported_by":graph.get("reverse",{}).get(rel,[]),"neighborhood":neighborhood(graph,[rel],depth=depth),"unresolved_relative_imports":graph.get("unresolved",{}).get(rel,[])}


def changed_view(index:dict[str,Any],changed:list[str],depth:int=1,top_k:int=40)->dict[str,Any]:
    existing=[p for p in changed if p in index["by_path"]]; affected=set(neighborhood(index["graph"],existing,depth=depth)); ranked=[f for f in index["files"] if f["path"] in affected]; return {"changed_files":changed,"indexed_changed_files":existing,"affected_depth":depth,"affected_files":[compact_file(f) for f in ranked[:max(1,top_k)]]}
