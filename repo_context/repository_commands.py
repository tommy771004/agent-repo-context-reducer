from __future__ import annotations
import argparse, pathlib
from typing import Any
from .admission import evaluate_read
from .git_utils import changed_files
from .graph import neighborhood
from .scanner import changed_view, dependency_view, module_map, project_map, query_view
REPOSITORY_VIEW_COMMANDS={"map","scan","query","module","deps","callers","impact","changed","admit"}
def handle_repository_view(args: argparse.Namespace,index: dict[str,Any])->dict[str,Any]:
    if args.command in {"map","scan"}: return project_map(index,top_k=args.top_k,query=args.query)
    if args.command=="query": return query_view(index,args.query,top_k=args.top_k)
    if args.command=="module": return module_map(index,args.module,top_k=args.top_k,query=args.query)
    if args.command=="deps":
        result=dependency_view(index,args.file,depth=args.depth); result["graph_semantics"]="resolved static import graph; not a runtime call graph"; return result
    if args.command=="callers":
        rel=pathlib.PurePosixPath(args.file).as_posix().lstrip("./")
        if rel not in index["by_path"]: raise ValueError(f"File not indexed: {rel}")
        return {"path":rel,"statically_imported_by":index["graph"].get("reverse",{}).get(rel,[]),"confidence":"high-for-resolved-static-imports","not_provided":"runtime callers"}
    if args.command=="impact":
        rel=pathlib.PurePosixPath(args.file).as_posix().lstrip("./")
        if rel not in index["by_path"]: raise ValueError(f"File not indexed: {rel}")
        affected=set(neighborhood(index["graph"],[rel],depth=args.depth)); ranked=[f for f in index["files"] if f["path"] in affected]
        return {"seed":rel,"depth":args.depth,"affected_files":[f["path"] for f in ranked[:args.top_k]],"classification":"static-dependency-neighborhood","runtime_impact_guarantee":False}
    if args.command=="changed": return changed_view(index,changed_files(pathlib.Path(args.path).resolve(),base=args.base),depth=args.depth,top_k=args.top_k)
    if args.command=="admit": return evaluate_read(index,args.file,args.task,session=args.session,requested=args.requested)
    raise ValueError(f"Unknown repository command: {args.command}")
