from __future__ import annotations

import math
import re
from typing import Any

from .concepts import expand_terms

STOP_WORDS = {"the","a","an","and","or","to","of","in","for","on","with","is","are","this","that","it","be","as","at","by","from","project","repo","repository","code","file","files","why","how","find","help","please","read","analyze","analyse","entire","whole","issue","problem"}

def query_terms(query: str | None) -> list[str]:
    if not query: return []
    terms=[t.lower() for t in re.findall(r"[A-Za-z0-9_\-\.]+|[\u4e00-\u9fff]{1,8}", query)]
    return [t for t in terms if len(t)>1 and t not in STOP_WORDS][:40]

def lexical_score(file: dict[str, Any], terms: list[str]) -> float:
    if not terms: return 0.0
    path=file["path"].lower(); symbols=" ".join(file.get("symbols",[])+file.get("classes",[])+file.get("types",[])+file.get("functions",[])+file.get("routes",[])).lower(); imports=" ".join(file.get("imports",[])).lower(); score=0.0
    for term in terms:
        if term in path: score+=8.0
        if term in symbols: score+=5.0
        if term in imports: score+=2.0
    return score

def rank_files(files: list[dict[str, Any]], graph: dict[str, Any], entry_points: list[str], query: str | None = None) -> list[dict[str, Any]]:
    terms=query_terms(query); expanded=expand_terms(terms); concept_terms=[t for t in expanded if t not in set(terms)]; degree=graph.get("degree",{})
    from .graph import distances_from_entries
    distances=distances_from_entries(graph, entry_points); ranked=[]
    for f in files:
        p=f["path"]; d=degree.get(p,{"in":0,"out":0}); static=float(f.get("static_importance",0)); centrality=math.log2(1+d.get("in",0))*7+math.log2(1+d.get("out",0))*3; entry_bonus=15.0 if f.get("entry_point") else 0.0; distance_bonus=max(0.0,8.0-distances[p]*1.5) if p in distances else 0.0; lexical=lexical_score(f,terms)+lexical_score(f,concept_terms)*0.35
        total=static*0.45+centrality*0.85+entry_bonus*0.35+distance_bonus*0.75+lexical*1.8 if terms else static+centrality+entry_bonus+distance_bonus
        reasons=[]
        if f.get("entry_point"): reasons.append("entry-point")
        if d.get("in",0): reasons.append(f"imported-by:{d['in']}")
        if d.get("out",0): reasons.append(f"imports:{d['out']}")
        if lexical: reasons.append(f"query-match:{round(lexical,1)}")
        if p in distances: reasons.append(f"entry-distance:{distances[p]}")
        ranked.append({**f,"rank_score":round(total,3),"rank_reasons":reasons})
    ranked.sort(key=lambda x:(-x["rank_score"],x["path"])); return ranked
