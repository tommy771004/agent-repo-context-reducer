from __future__ import annotations
import argparse, json, pathlib, sys
from typing import Any
from .benchmark import benchmark_tasks, load_tasks, benchmark_reducer_cases, load_benchmark_cases
from .command_facade import get_facade, list_facades
from .capabilities import detect_providers, doctor, resolve_capability
from .context_command import execute_context
from .index_runtime import index_kwargs, persistent_index
from .repository_commands import REPOSITORY_VIEW_COMMANDS, handle_repository_view
from .repository_runtime import inspect_file, symbol_with_ledger
_symbol_with_ledger = symbol_with_ledger
from .config import load_config, trust_provider, prefer_provider
from .delegate import delegate_capability
from .external_context import load_external_file
from .fanout import recommend_fanout
from .fan_in import reduce_worker_outputs, reduce_worker_stream
from .filter_audit import audit_filter_reduction
from .model_packet import split_model_packet
from .adaptive_reduction import choose_reduction_mode
from .scenario_simulation import simulate_scenarios
from .synthesis_packet import build_synthesis_packet
from .streaming import iter_worker_input
from .tokenizer import tokenizer_status, token_estimate
from .candidate_detection import analyze_candidates, candidate_provider_status
from .git_provenance import repository_provenance, file_provenance, symbol_provenance
from .schema_registry import list_schemas, load_schema, validate_contract
from .trust_boundary import classify_untrusted_text
from .handoff import reduce_handoff
from .host_adapters import install_host_commands, host_status, uninstall_host_commands
from .indexer import build_persistent, ensure_index, index_status
from .orchestration import plan_harness
from .runtime_adapters import runtime_adapter_status
from .runtime_engine import execute_runtime, load_runtime_config
from .runtime_state import RuntimeCheckpointStore, list_runtime_runs
from .answer_evaluation import evaluate_final_answer
from .context_planner import build_context
from .trace import new_run_id
from .provider_health import ProviderHealth
from .router import route_task
from .scheduler import build_schedule
from .tool_policy import classify_command
from .trace import replay_summary
from .complexity import classify_complexity
from .artifact_store import ArtifactStore
from .grader import build_grade_packet, evaluate_grade
from .knowledge import build_knowledge_index, search_knowledge, knowledge_status
from .retry_policy import decide_retry
from .maintenance import HOSTS, remove_artifacts, remove_shortcuts, remove_state, self_update_hint, state_inventory, update_index, update_shortcuts
from .task_budget import BudgetLimits, TaskBudget
from .lifecycle import ContextLifecycle
from .attribution import analyze_context_usage
from .cli_parser import build_parser


def _load_user_payload(value: str) -> Any:
    p=pathlib.Path(value)
    if p.is_file():
        text=p.read_text(encoding='utf-8',errors='replace')
        try:return json.loads(text)
        except json.JSONDecodeError:return text
    try:return json.loads(value)
    except json.JSONDecodeError:return value


def _print(result: Any, pretty: bool=False):
    print(json.dumps(result,ensure_ascii=False,indent=2 if pretty else None,separators=None if pretty else (',',':')))


def main(argv:list[str]|None=None)->int:
    args=build_parser().parse_args(argv)
    try:
        if args.command=='run':
            spec=get_facade(args.facade)
            forwarded=['doctor',args.repo] if spec.mode=='doctor' else ['context',args.repo,args.task.strip() or spec.default_task,'--budget',str(args.budget or spec.default_budget),'--session',args.session]
            if spec.mode!='doctor' and spec.intent: forwarded.extend(['--intent',spec.intent])
            if args.pretty: forwarded.append('--pretty')
            return main(forwarded)
        if args.command=='commands': _print({'commands':list_facades(),'human_interface':'Use /reducer-* in Claude Code after host-install; Codex gets named reducer-* skills.'},args.pretty); return 0
        if args.command=='host-install': _print(install_host_commands(args.repo,args.host,scope=args.scope,dry_run=args.dry_run),args.pretty); return 0
        if args.command=='host-status': _print(host_status(args.repo,args.host,scope=args.scope),args.pretty); return 0
        if args.command=='host-uninstall': _print(uninstall_host_commands(args.repo,args.host,scope=args.scope,yes=args.yes,force=args.force),args.pretty); return 0
        if args.command=='update':
            hosts=tuple(args.host) if args.host else HOSTS; scopes=tuple(args.scope) if args.scope else ('project',); sections={}
            if args.target in {'all','index'}:
                sections['index']={'target':'index','dry_run':True,**index_status(pathlib.Path(args.repo).resolve())} if args.dry_run else update_index(args.repo,max_files=args.max_files,max_file_bytes=args.max_file_bytes,include_hidden=args.include_hidden,use_cache=not args.no_cache,include_generated=args.include_generated)
            if args.target in {'all','shortcuts'}: sections['shortcuts']=update_shortcuts(args.repo,hosts=hosts,scopes=scopes,dry_run=args.dry_run)
            if args.target in {'all','self'}: sections['self']=self_update_hint(args.repo)
            _print({'command':'update','target':args.target,'dry_run':args.dry_run,**sections},args.pretty); return 0
        if args.command=='remove':
            hosts=tuple(args.host) if args.host else HOSTS; scopes=tuple(args.scope) if args.scope else ('project',); sections={}
            if args.target in {'all','state'}: sections['state']=remove_state(args.repo,yes=args.yes,include_preserved=args.include_preserved)
            if args.target in {'all','shortcuts'}: sections['shortcuts']=remove_shortcuts(args.repo,hosts=hosts,scopes=scopes,yes=args.yes,force=args.force)
            if args.target in {'all','artifacts'}: sections['artifacts']=remove_artifacts(args.repo,yes=args.yes)
            _print({'command':'remove','target':args.target,'dry_run':not args.yes,'inventory':state_inventory(args.repo) if args.target in {'all','state'} else None,**sections},args.pretty); return 0
        if args.command=='complexity': result=classify_complexity(args.task,args.intent)
        elif args.command=='plan': result=plan_harness(args.task,args.repo,forced_type=args.intent,context_tokens=args.context_budget,output_tokens=args.output_budget,model_calls=args.model_calls)
        elif args.command=='schedule': result=build_schedule(args.task,args.intent)
        elif args.command=='runtime':
            if args.action=='status':
                result={
                    "adapters":runtime_adapter_status(),
                    "execution_policy":{
                        "subprocess_requires_allow_external_commands":True,
                        "container_network_default":"none",
                        "container_repository_default":"read-only",
                        "network_requires_allow_runtime_network":True,
                        "repository_write_requires_allow_runtime_write":True,
                        "shell":False,"cost_inference":False,
                        "checkpoint_default":True,
                    },
                }
            elif args.action=='list':
                result={"runs":list_runtime_runs(args.repo,args.limit)}
            elif args.action=='inspect':
                if not args.task: raise ValueError('runtime inspect requires RUN_ID')
                result=RuntimeCheckpointStore(args.repo,args.task).summary()
            elif args.action=='resume':
                if not args.task: raise ValueError('runtime resume requires RUN_ID')
                if not args.config: raise ValueError('runtime resume requires --config')
                rid=args.task
                checkpoint_data=RuntimeCheckpointStore(args.repo,rid).load()
                task=str(checkpoint_data.get('task') or '')
                if not task: raise ValueError('runtime checkpoint does not contain a task')
                settings=checkpoint_data.get('resume_settings') if isinstance(checkpoint_data.get('resume_settings'),dict) else {}
                config=load_runtime_config(args.config)
                context_pack=None
                if args.context_json:
                    context_pack=_load_user_payload(args.context_json)
                    if not isinstance(context_pack,dict): raise ValueError('--context-json must contain a JSON object')
                elif bool(settings.get('context_present')):
                    idx=ensure_index(args.repo,sync=True,use_cache=True)["index"]
                    context_pack=build_context(idx,task,budget=int(settings.get('context_tokens',12000)),session=f"runtime-{rid}",tokenizer=str(settings.get('tokenizer') or 'native'),tokenizer_model=settings.get('tokenizer_model'))
                final_case=_load_user_payload(args.final_case) if args.final_case else checkpoint_data.get('final_answer_case')
                if final_case is not None and not isinstance(final_case,dict): raise ValueError('--final-case must contain a JSON object')
                result=execute_runtime(
                    task,args.repo,runtime_config=config,adapter_name=args.adapter or checkpoint_data.get('adapter'),forced_type=settings.get('forced_type'),context_pack=context_pack,
                    context_tokens=int(settings.get('context_tokens',12000)),output_tokens=int(settings.get('output_tokens',4000)),model_calls=int(settings.get('model_calls',10)),
                    concurrency=args.concurrency,authorize_external=args.allow_external_commands,authorize_network=args.allow_runtime_network,authorize_write=args.allow_runtime_write,
                    fail_fast=bool(settings.get('fail_fast',True)),resume=True,allow_repo_drift=args.allow_repo_drift,checkpoint=not args.no_checkpoint,run_id=rid,
                    tokenizer=str(settings.get('tokenizer') or 'native'),tokenizer_model=settings.get('tokenizer_model'),synthesis_budget=int(settings.get('synthesis_budget',6000)),final_answer_case=final_case,reduction_mode=(args.reduction_mode or settings.get('reduction_mode') or 'compat'),
                )
            else:
                if not args.task: raise ValueError('runtime execute requires TASK')
                if not args.config: raise ValueError('runtime execute requires --config')
                config=load_runtime_config(args.config)
                rid=args.run_id or new_run_id()
                context_pack=None
                if args.context_json:
                    context_pack=_load_user_payload(args.context_json)
                    if not isinstance(context_pack,dict): raise ValueError('--context-json must contain a JSON object')
                elif not args.no_context:
                    idx=ensure_index(args.repo,sync=True,use_cache=True)["index"]
                    context_pack=build_context(idx,args.task,budget=args.context_budget,session=f"runtime-{rid}",tokenizer=args.tokenizer,tokenizer_model=args.tokenizer_model)
                final_case=_load_user_payload(args.final_case) if args.final_case else None
                if final_case is not None and not isinstance(final_case,dict): raise ValueError('--final-case must contain a JSON object')
                result=execute_runtime(
                    args.task,args.repo,runtime_config=config,adapter_name=args.adapter,forced_type=args.intent,context_pack=context_pack,context_tokens=args.context_budget,output_tokens=args.output_budget,model_calls=args.model_calls,concurrency=args.concurrency,
                    authorize_external=args.allow_external_commands,authorize_network=args.allow_runtime_network,authorize_write=args.allow_runtime_write,fail_fast=not args.keep_going,checkpoint=not args.no_checkpoint,run_id=rid,tokenizer=args.tokenizer,tokenizer_model=args.tokenizer_model,synthesis_budget=args.synthesis_budget,final_answer_case=final_case,reduction_mode=args.reduction_mode,
                )
        elif args.command=='evaluate-final':
            case=_load_user_payload(args.case)
            if not isinstance(case,dict): raise ValueError('evaluate-final CASE must be a JSON object or JSON file')
            result=evaluate_final_answer(_load_user_payload(args.answer),case)
        elif args.command=='quality':
            if args.action=='packet':
                if args.input is None: raise ValueError('quality packet requires TASK and INPUT')
                result=build_grade_packet(args.value,_load_user_payload(args.input),task_type=args.intent,artifact_id=args.artifact_id)
            else:
                if not args.risk_level: raise ValueError('quality evaluate requires --risk-level')
                payload=_load_user_payload(args.value)
                if not isinstance(payload,dict): raise ValueError('quality evaluate expects a JSON object or JSON file')
                result=evaluate_grade(payload,risk_level=args.risk_level)
        elif args.command=='retry-decision': result=decide_retry(decision=args.decision,attempt=args.attempt,worker_tier=args.worker_tier,risk_level=args.risk_level,complexity_level=args.complexity_level,force_escalation=args.force_escalation)
        elif args.command=='fan-in':
            records,input_meta=iter_worker_input(args.input,input_format=args.format)
            candidate_provider=None if args.no_candidate_dedup else args.candidate_provider
            if input_meta.get('streaming'):
                reduction=reduce_worker_stream(records,min_confidence=args.min_confidence,detect_conflicts=not args.no_conflicts,tokenizer=args.tokenizer,tokenizer_model=args.tokenizer_model,malformed_detail_limit=args.malformed_detail_limit,filtered_detail_limit=args.filtered_detail_limit,candidate_provider=candidate_provider,candidate_threshold=args.candidate_threshold,max_candidate_pairs=args.max_candidate_pairs,trust_policy=args.trust_policy,unstructured_canonical_policy=args.unstructured_canonical_policy)
            else:
                worker_outputs=list(records)
                reduction=reduce_worker_outputs(worker_outputs,min_confidence=args.min_confidence,detect_conflicts=not args.no_conflicts,tokenizer=args.tokenizer,tokenizer_model=args.tokenizer_model,candidate_provider=candidate_provider,candidate_threshold=args.candidate_threshold,max_candidate_pairs=args.max_candidate_pairs,trust_policy=args.trust_policy,unstructured_canonical_policy=args.unstructured_canonical_policy,malformed_detail_limit=args.malformed_detail_limit,filtered_detail_limit=args.filtered_detail_limit)
            filter_audit=audit_filter_reduction(reduction)
            result={'input':input_meta,'reduction':reduction,'filter_audit':filter_audit,'synthesis_packet':build_synthesis_packet(reduction,max_estimated_tokens=args.budget,tokenizer=args.tokenizer,tokenizer_model=args.tokenizer_model)}
        elif args.command=='synthesis-packet':
            payload=_load_user_payload(args.input)
            if isinstance(payload,dict) and isinstance(payload.get('reduction'),dict): payload=payload['reduction']
            if not isinstance(payload,dict): raise ValueError('synthesis-packet input must be a fan-in reduction object')
            result=build_synthesis_packet(payload,max_estimated_tokens=args.budget,tokenizer=args.tokenizer,tokenizer_model=args.tokenizer_model)
        elif args.command=='filter-audit':
            payload=_load_user_payload(args.input)
            if isinstance(payload,dict) and isinstance(payload.get('reduction'),dict): payload=payload['reduction']
            if not isinstance(payload,dict): raise ValueError('filter-audit input must be a fan-in reduction object')
            result=audit_filter_reduction(payload)
        elif args.command=='model-packet':
            payload=_load_user_payload(args.input)
            if not isinstance(payload,dict): raise ValueError('model-packet input must be a synthesis packet object')
            result=split_model_packet(payload,tokenizer=args.tokenizer,tokenizer_model=args.tokenizer_model)
        elif args.command=='reduction-route':
            result=choose_reduction_mode(args.task,source_tokens=args.source_tokens,duplicate_ratio=args.duplicate_ratio,conflict_ratio=args.conflict_ratio,task_type=args.intent,requires_parallel_evidence=args.parallel_evidence)
        elif args.command=='simulate-reduction':
            scenarios=None
            if args.scenarios_json:
                payload=_load_user_payload(args.scenarios_json)
                if not isinstance(payload,list): raise ValueError('simulate-reduction input must be a JSON array')
                scenarios=[row for row in payload if isinstance(row,dict)]
            result=simulate_scenarios(scenarios)
        elif args.command=='tokenizer':
            if args.action=='status': result={'tokenizers':tokenizer_status()}
            else:
                if args.input is None: raise ValueError('tokenizer estimate requires INPUT')
                result=token_estimate(_load_user_payload(args.input),tokenizer=args.provider,model=args.model)
        elif args.command=='candidate-detect':
            payload=_load_user_payload(args.input)
            if isinstance(payload,dict) and isinstance(payload.get('reduction'),dict): payload=payload['reduction']
            findings=payload.get('findings') if isinstance(payload,dict) else payload
            if not isinstance(findings,list): raise ValueError('candidate-detect input must be a findings array or reduction object')
            result=analyze_candidates(findings,provider=args.provider,threshold=args.threshold,max_pairs=args.max_pairs)
            result['available_providers']=candidate_provider_status()
        elif args.command=='provenance':
            if args.action=='repo': result=repository_provenance(args.repo)
            elif args.action=='file':
                if not args.path: raise ValueError('provenance file requires PATH')
                result=file_provenance(args.repo,args.path)
            else:
                if not args.path or not args.symbol: raise ValueError('provenance symbol requires PATH SYMBOL')
                result=symbol_provenance(args.repo,args.path,args.symbol,start_line=args.start_line,end_line=args.end_line,fingerprint=args.fingerprint)
        elif args.command=='schema':
            if args.action=='list': result={'schemas':list_schemas()}
            elif args.action=='get':
                if not args.name: raise ValueError('schema get requires NAME')
                result=load_schema(args.name)
            else:
                if not args.name or not args.input: raise ValueError('schema validate requires NAME INPUT')
                result=validate_contract(args.name,_load_user_payload(args.input))
        elif args.command=='trust-scan':
            target=pathlib.Path(args.input)
            text=target.read_text(encoding='utf-8',errors='replace') if target.is_file() else args.input
            result=classify_untrusted_text(text,source=args.source)
        elif args.command=='benchmark-e2e':
            result=benchmark_reducer_cases(load_benchmark_cases(pathlib.Path(args.cases_json)),default_synthesis_budget=args.budget,tokenizer=args.tokenizer,tokenizer_model=args.tokenizer_model)
        elif args.command=='handoff':
            root=pathlib.Path(args.repo).resolve(); payload=_load_user_payload(args.input); artifact_id=None
            if args.store_artifact: artifact_id=ArtifactStore(root).put(payload,kind='agent-output',producer=args.from_role)['id']
            result=reduce_handoff(payload,from_role=args.from_role,to_role=args.to_role,task=args.task,artifact_id=artifact_id,token_budget=args.token_budget,tokenizer=args.tokenizer,tokenizer_model=args.tokenizer_model)
        elif args.command=='artifact':
            store=ArtifactStore(pathlib.Path(args.repo).resolve())
            if args.action=='put':
                if not args.value: raise ValueError('artifact put requires a value')
                result=store.put(_load_user_payload(args.value),kind=args.kind,producer=args.producer)
            elif args.action=='get':
                if not args.value: raise ValueError('artifact get requires an id')
                result=store.view(args.value,include_payload=args.payload)
            elif args.action=='remove':
                if not args.value: raise ValueError('artifact remove requires an id')
                result=store.remove(args.value)
            else: result={'artifacts':store.list(args.limit)}
        elif args.command=='knowledge':
            if args.action=='index': result=build_knowledge_index(args.repo)
            elif args.action=='status': result=knowledge_status(args.repo)
            else:
                if not args.query: raise ValueError('knowledge search requires a query')
                result=search_knowledge(args.repo,args.query,top_k=args.top_k,budget=args.budget)
        elif args.command=='inspect': result=inspect_file(args.path,args.max_file_bytes)
        elif args.command=='detect': result=detect_providers(args.path,required=args.capability,use_cache=not args.no_cache)
        elif args.command=='doctor': result=doctor(args.path)
        elif args.command=='resolve': result=resolve_capability(args.path,args.capability,allow_external_commands=args.allow_external_commands)
        elif args.command=='delegate': result=delegate_capability(args.path,args.capability,args.task,allow_external_commands=args.allow_external_commands,timeout_seconds=args.timeout)
        elif args.command=='provider-health': result={'providers':ProviderHealth(pathlib.Path(args.path).resolve()).summary(args.provider)}
        elif args.command=='provider-trust': result=trust_provider(pathlib.Path(args.path).resolve(),args.provider_id,True)
        elif args.command=='provider-untrust': result=trust_provider(pathlib.Path(args.path).resolve(),args.provider_id,False)
        elif args.command=='provider-prefer':
            root=pathlib.Path(args.path).resolve()
            if args.provider_id not in set(load_config(root).get('trusted_providers',[])): raise ValueError('Preferred external provider must be trusted first')
            result=prefer_provider(root,args.capability,args.provider_id)
        elif args.command=='provider-config': result=load_config(pathlib.Path(args.path).resolve())
        elif args.command=='route': result=route_task(args.task,None if args.no_resolve else args.repo)
        elif args.command=='ingest': result={'provider':args.provider,'blocks':load_external_file(pathlib.Path(args.json_file),args.provider)}
        elif args.command=='status': result=index_status(args.path)
        elif args.command=='index':
            built=build_persistent(args.path,**index_kwargs(args)); result={'mode':built['mode'],'index_path':built['path'],**index_status(args.path),'stats':built['index'].get('stats',{})}
        elif args.command=='sync':
            synced=ensure_index(args.path,sync=True,**index_kwargs(args)); result={'mode':synced['mode'],'index_path':synced['path'],**index_status(args.path),'sync_stats':synced['index'].get('sync_stats',{})}
        elif args.command=='symbol': result=symbol_with_ledger(pathlib.Path(args.path).resolve(),args.file,args.symbol,args.session,args.max_file_bytes)
        elif args.command=='tool-policy': result=classify_command(args.command_line)
        elif args.command=='fanout': result=recommend_fanout(args.coverage,args.unresolved,args.used_subagents,args.max_subagents,args.concurrency)
        elif args.command=='budget':
            limits=BudgetLimits(context_tokens=args.limit_context,output_tokens=args.limit_output,tool_calls=args.limit_tools,model_calls=args.limit_models,subagents=args.limit_subagents,wall_seconds=args.limit_wall); b=TaskBudget(pathlib.Path(args.path).resolve(),args.run_id,limits=limits)
            if args.action=='consume': result=b.consume(context_tokens=args.context_tokens,output_tokens=args.output_tokens,tool_calls=args.tool_calls,model_calls=args.model_calls,subagents=args.subagents)
            else: b.save(); result=b.status()
        elif args.command=='lifecycle':
            life=ContextLifecycle(pathlib.Path(args.path).resolve(),args.session)
            result=life.evict(args.max_hot_tokens) if args.action=='evict' else {'session':args.session,'tiers':life.classify(),'items':life.data['items']}
            life.save()
        elif args.command=='replay': result=replay_summary(pathlib.Path(args.path).resolve(),args.run_id)
        elif args.command=='benchmark': result=benchmark_tasks(pathlib.Path(args.path).resolve(),load_tasks(pathlib.Path(args.tasks_json)),args.budget)
        elif args.command=='analyze-context': result=analyze_context_usage(json.loads(pathlib.Path(args.context_json).read_text(encoding='utf-8')),pathlib.Path(args.answer_file).read_text(encoding='utf-8',errors='replace'))
        elif args.command=='context': result=execute_context(args)
        elif args.command in REPOSITORY_VIEW_COMMANDS: result=handle_repository_view(args,persistent_index(args))
        else: raise ValueError(f'Unknown command: {args.command}')
        _print(result,getattr(args,'pretty',False))
        if args.command == 'runtime' and getattr(args, 'action', None) in {'execute','resume'} and isinstance(result, dict) and not result.get('success', False):
            return 3
        if args.command == 'evaluate-final' and isinstance(result, dict) and not result.get('passed', False):
            return 3
        if args.command == 'filter-audit' and isinstance(result, dict) and not result.get('passed', False):
            return 3
        if args.command == 'fan-in' and isinstance(result, dict) and isinstance(result.get('filter_audit'), dict) and not result['filter_audit'].get('passed', False):
            return 3
        return 0
    except (ValueError,OSError,json.JSONDecodeError) as exc:
        print(f'error: {exc}',file=sys.stderr); return 2

if __name__=='__main__': raise SystemExit(main())
