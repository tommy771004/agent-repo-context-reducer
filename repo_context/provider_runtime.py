from __future__ import annotations

import pathlib
import subprocess
import time
from typing import Any

from .capabilities import resolve_capability
from .provider_health import ProviderHealth


def search_repository(root: pathlib.Path, query: str, max_results: int = 50) -> dict[str, Any]:
    resolution=resolve_capability(root,"repository.search"); selected=resolution["selected"]
    if selected.get("id")!="cli:rg": return {"used":False,"resolution":resolution,"results":[]}
    started=time.perf_counter()
    proc=subprocess.run([selected["source"],"-n","--no-heading","--color","never","-m","3",query,str(root)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8",errors="replace",check=False)
    latency_ms=(time.perf_counter()-started)*1000
    ProviderHealth(root).record(selected.get("id","cli:rg"),proc.returncode in (0,1),latency_ms)
    rows=[]
    for line in proc.stdout.splitlines()[:max_results]:
        parts=line.split(":",2)
        if len(parts)==3:
            p,ln,text=parts
            try: rel=pathlib.Path(p).resolve().relative_to(root.resolve()).as_posix()
            except Exception: rel=p.replace("\\","/")
            rows.append({"path":rel,"line":int(ln) if ln.isdigit() else None,"text":text[:500]})
    return {"used":True,"resolution":resolution,"results":rows,"exit_code":proc.returncode,"latency_ms":round(latency_ms,2)}
