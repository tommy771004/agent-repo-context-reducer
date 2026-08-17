from __future__ import annotations
import math
from typing import Any
def value_of_information(*,relevance:float,uncertainty:float,novelty:float,graph_distance:int|None,estimated_tokens:int)->dict[str,Any]:
    proximity=1.0 if graph_distance is None else 1.0/(1.0+max(0,graph_distance));cost=max(1.0,math.log2(max(2,estimated_tokens)));score=max(0.0,relevance)*max(0.05,uncertainty)*max(0.05,novelty)*(0.5+proximity)/cost
    return {"score":round(score,6),"classification":"heuristic-value-of-information","components":{"relevance":round(relevance,4),"uncertainty":round(uncertainty,4),"novelty":round(novelty,4),"graph_proximity":round(proximity,4),"estimated_tokens":int(estimated_tokens)}}
