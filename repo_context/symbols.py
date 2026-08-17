from __future__ import annotations
import ast,hashlib,pathlib,re
from typing import Any
from .util import safe_read_text

def _hash(text:str)->str:return hashlib.sha256(text.encode("utf-8")).hexdigest()
def _python_symbols(text:str)->list[dict[str,Any]]:
    try:tree=ast.parse(text)
    except SyntaxError:return []
    out=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.ClassDef):out.append({"name":node.name,"kind":"class","start_line":node.lineno,"end_line":getattr(node,"end_lineno",node.lineno)})
        elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            args=[a.arg for a in node.args.args]; out.append({"name":node.name,"kind":"function","signature":f"{node.name}({', '.join(args)})","start_line":node.lineno,"end_line":getattr(node,"end_lineno",node.lineno)})
    return out
def _brace_end(lines,start,limit=500):
    depth=0;seen=False
    for i in range(start-1,min(len(lines),start-1+limit)):
        line=lines[i]
        if "{" in line:seen=True
        depth+=line.count("{")-line.count("}")
        if seen and depth<=0:return i+1
    return min(len(lines),start+80)
def _statement_end(lines,start,limit=200):
    for i in range(start-1,min(len(lines),start-1+limit)):
        if ";" in lines[i]:return i+1
    return min(len(lines),start)
SHARED_PATTERNS=[("class",re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:public\s+|private\s+|protected\s+|internal\s+|abstract\s+|sealed\s+|static\s+)*class\s+([A-Za-z_]\w*)")),("type",re.compile(r"^\s*(?:export\s+)?(?:interface|type|enum|record|trait|struct)\s+([A-Za-z_]\w*)")),("function",re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:public\s+|private\s+|protected\s+|internal\s+|static\s+|async\s+|pub\s+)*function\s+([A-Za-z_]\w*)\s*\(")),("function",re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_]\w*)\s*=>")),("function",re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)\s*\(")),("function",re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\("))]
EXT_PATTERNS={"c":[("function",re.compile(r"^\s*(?:[A-Za-z_][\w:<>,\s\*&]*?[\s\*&])([A-Za-z_]\w*)\s*\([^;]*\)\s*(?:const\s*)?\{"))],"shell":[("function",re.compile(r"^\s*(?:function\s+)?([A-Za-z_][\w-]*)\s*\(\s*\)\s*\{")),("function",re.compile(r"^\s*function\s+([A-Za-z_][\w-]*)\s*\{"))],"ps":[("function",re.compile(r"^\s*function\s+([A-Za-z_][\w-]*)",re.I))],"sql":[("type",re.compile(r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)\s+|GLOBAL\s+|UNIQUE\s+|MATERIALIZED\s+)?(?:TABLE|VIEW|TYPE|SCHEMA|INDEX|TRIGGER|PROCEDURE|FUNCTION)\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][\w.]*)",re.I))]}
C_EXTS={".c",".h",".cc",".cpp",".hpp"};SHELL_EXTS={".sh",".bash",".zsh"};C_NON_FUNCTIONS={"if","for","while","switch","catch","return","sizeof","do","else"}
def _pattern_group(ext):
    if ext in C_EXTS:return "c"
    if ext in SHELL_EXTS:return "shell"
    if ext==".ps1":return "ps"
    if ext==".sql":return "sql"
def _heuristic_symbols(path,text):
    lines=text.splitlines();out=[];group=_pattern_group(pathlib.Path(path).suffix.lower());patterns=SHARED_PATTERNS+EXT_PATTERNS.get(group or "",[])
    for no,line in enumerate(lines,1):
        for kind,pat in patterns:
            m=pat.search(line)
            if m:
                if group=="c" and m.group(1) in C_NON_FUNCTIONS:continue
                end=_statement_end(lines,no) if group=="sql" else _brace_end(lines,no);out.append({"name":m.group(1),"kind":kind,"signature":line.strip()[:220],"start_line":no,"end_line":end});break
    return out
def extract_symbol_index(path,text):
    ext=pathlib.Path(path).suffix.lower();symbols=_python_symbols(text) if ext==".py" else _heuristic_symbols(path,text);lines=text.splitlines();result=[]
    for sym in symbols:
        start,end=sym["start_line"],sym["end_line"];chunk="\n".join(lines[start-1:end]);result.append({**sym,"fingerprint":_hash(chunk),"estimated_tokens":max(1,len(chunk.encode("utf-8"))//4)})
    return result
def read_symbol(root,file_path,symbol,max_file_bytes=2_000_000):
    path=(root/file_path).resolve()
    try:path.relative_to(root.resolve())
    except ValueError:raise ValueError("Symbol path escapes repository root")
    text,_,reason=safe_read_text(path,max_file_bytes)
    if text is None:raise ValueError(f"Cannot read symbol source ({reason}): {file_path}")
    index=extract_symbol_index(file_path,text);matches=[s for s in index if s["name"]==symbol or f"{pathlib.PurePosixPath(file_path).stem}.{s['name']}"==symbol]
    if not matches:matches=[s for s in index if symbol.lower() in s["name"].lower()]
    if not matches:raise ValueError(f"Symbol not found in {file_path}: {symbol}")
    sym=matches[0];lines=text.splitlines();chunk="\n".join(lines[sym["start_line"]-1:sym["end_line"]]);return {**sym,"path":file_path,"content":chunk,"fingerprint":_hash(chunk),"estimated_tokens":max(1,len(chunk.encode("utf-8"))//4)}
