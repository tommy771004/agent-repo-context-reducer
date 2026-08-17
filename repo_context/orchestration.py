from __future__ import annotations
import pathlib
from typing import Any
from .capabilities import NATIVE_CAPABILITIES, resolve_capability
from .complexity import classify_complexity
from .grader import grade_policy
from .lane_budget import allocate_lane_budgets
from .model_router import route_models
from .retry_policy import retry_policy
from .risk import classify_risk
from .router import route_task
from .scheduler import build_schedule

def capability_layer(capability: str) -> str:
    return capability.split('.',1)[0] if '.' in capability else 'other'

def plan_harness(task: str, repo: pathlib.Path | str='.', forced_type: str | None=None, *, context_tokens:int=12000, output_tokens:int=4000, model_calls:int=10, route_result:dict[str,Any]|None=None)->dict[str,Any]:
    root=pathlib.Path(repo).resolve(); route=route_result or route_task(task,repo=None,forced_type=forced_type); task_type=route['task_type']
    complexity=route.get('complexity') or classify_complexity(task,task_type); risk=route.get('risk') or classify_risk(task,task_type)
    model_policy=route_models(task,task_type,repo=root); schedule=build_schedule(task,task_type,complexity_result=complexity,risk_result=risk)
    lane_budget=allocate_lane_budgets(schedule,model_policy,context_tokens=context_tokens,output_tokens=output_tokens,model_calls=model_calls)
    retry=retry_policy(risk['level'],complexity['level']); quality=grade_policy(risk['level']); quality['model_tier']=model_policy['roles'].get('grader','standard')
    required=list(route['required_capabilities'])
    optional=['harness.complexity','harness.risk-routing','harness.model-routing','orchestration.scheduler','context.lane-budget','quality.gate','harness.retry-policy']
    if complexity['multi_agent_recommended']:
        optional += ['context.handoff','context.artifact','context.fan-in','context.contradiction','context.synthesis-packet','orchestration.handoff','quality.grader']
    if complexity['level'] in {'complex','autonomous'}: optional += ['knowledge.search']
    if complexity['level']=='autonomous': optional += ['executor.autonomous']
    optional += [f"model.{tier}" for tier in sorted(set(model_policy['roles'].values()))]
    resolutions={}; existing=route.get('provider_resolution') or {}; model_resolutions={f"model.{tier}":value for tier,value in model_policy.get('provider_resolution',{}).items()}
    for cap in dict.fromkeys(required+optional): resolutions[cap]=existing.get(cap) or model_resolutions.get(cap) or resolve_capability(root,cap)
    by_layer={}; unresolved=[]; native_fallbacks=[]; reused=[]
    for cap,resolution in resolutions.items():
        layer=capability_layer(cap); selected=resolution.get('selected'); by_layer.setdefault(layer,{})[cap]=selected
        if not selected: unresolved.append(cap)
        elif selected.get('source_type')=='native': native_fallbacks.append(cap)
        else: reused.append(cap)
    return {'task':task,'route':route,'complexity':complexity,'risk':risk,'model_policy':model_policy,'schedule':schedule,'lane_budget':lane_budget,'quality_gate':quality,'retry_policy':retry,'capability_plan':{'required':required,'optional':list(dict.fromkeys(optional))},'provider_layers':by_layer,'external_capabilities_reused':reused,'native_fallback_capabilities':native_fallbacks,'unresolved_optional_capabilities':[c for c in unresolved if c in optional],'unresolved_required_capabilities':[c for c in unresolved if c in required],'policy':'Deterministic routing first -> reuse compatible providers -> abstract model tier only when a model call is needed -> native fallback where implemented.','native_support':sorted(NATIVE_CAPABILITIES)}
