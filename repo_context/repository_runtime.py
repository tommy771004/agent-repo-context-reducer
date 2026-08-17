from __future__ import annotations
import pathlib
from typing import Any
from .ledger import SessionLedger
from .parsers import summarize_source
from .symbols import read_symbol
from .util import SOURCE_EXTENSIONS, estimate_tokens_from_bytes, is_secret_path, safe_read_text

def inspect_file(path: str,max_bytes: int)->dict[str,Any]:
    p=pathlib.Path(path).expanduser().absolute()
    if is_secret_path(p.as_posix()): raise ValueError(f"Refusing to inspect secret-like path: {p}")
    if not p.is_file(): raise ValueError(f"Not a file: {p}")
    text,size,reason=safe_read_text(p,max_bytes)
    if text is None: raise ValueError(f"File unavailable ({reason}): {p}")
    summary=summarize_source(p.name,text)
    return {"path":str(p),"language":SOURCE_EXTENSIONS.get(p.suffix.lower()),"bytes":size,**summary,"estimated_raw_tokens":estimate_tokens_from_bytes(size)}

def symbol_with_ledger(root:pathlib.Path,file:str,name:str,session:str,max_bytes:int)->dict[str,Any]:
    item=read_symbol(root,file,name,max_file_bytes=max_bytes); ledger=SessionLedger(root,session=session); key=f"symbol:{item['path']}:{item['name']}:{item.get('start_line')}"; comparison=ledger.compare(key,item["fingerprint"],item["content"])
    if comparison["state"]=="unchanged": result={k:v for k,v in item.items() if k!="content"}; result.update({"content_mode":"omitted-unchanged","session":session,"already_seen":True})
    elif comparison["state"]=="changed" and comparison.get("diff") and len(comparison["diff"])<len(item["content"]): result={**item,"content":comparison["diff"],"content_mode":"delta","session":session,"already_seen":False}
    else: result={**item,"content_mode":"full-symbol","session":session,"already_seen":False}
    ledger.record(key,item["fingerprint"],item["content"]); ledger.save(); return result
