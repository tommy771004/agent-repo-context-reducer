from __future__ import annotations
import hashlib, math, pathlib
from typing import Any
from .capabilities import resolve_capability
from .external_context import deduplicate_blocks
from .ledger import SessionLedger
from .lifecycle import ContextLifecycle
from .provider_runtime import search_repository
from .ranking import rank_files, query_terms
from .scanner import compact_file
from .util import estimate_tokens_from_bytes, safe_read_text
from .voi import value_of_information


def _fingerprint(text:str)->str: return hashlib.sha256(text.encode('utf-8')).hexdigest()

def _symbol_score(sym:dict[str,Any],file_score:float,terms:list[str])->float:
    hay=' '.join([sym.get('name',''),sym.get('signature',''),sym.get('kind','')]).lower(); direct=0.0
    for t in terms:
        if t in hay: direct += 9.0 if t in sym.get('name','').lower() else 4.0
    return file_score*0.2+direct

def _read_record(root:pathlib.Path,record:dict[str,Any],max_file_bytes:int=2_000_000)->tuple[str|None,str|None]:
    path=(root/record['path']).resolve()
    try:path.relative_to(root.resolve())
    except ValueError:return None,'outside-root'
    text,_,reason=safe_read_text(path,max_file_bytes)
    if text is None:return None,reason or 'unreadable'
    lines=text.splitlines(); start=max(1,int(record.get('start_line',1))); end=min(len(lines),int(record.get('end_line',start)))
    return '\n'.join(lines[start-1:end]),None

def _coverage(terms:list[str],searchable:str)->dict[str,Any]:
    if not terms:return {'score':None,'matched':[],'missing':[],'classification':'not-applicable'}
    lower=searchable.lower(); matched=sorted({t for t in terms if t in lower}); missing=sorted({t for t in terms if t not in lower})
    return {'score':round(len(matched)/max(1,len(set(terms))),3),'matched':matched[:40],'missing':missing[:40],'classification':'heuristic-lexical-coverage'}

def _normalized_relevance(score:float)->float:return round(1.0-math.exp(-max(0.0,score)/24.0),5)

def _provider_resolution(root:pathlib.Path)->dict[str,Any]:
    caps=['repository.search','repository.graph','repository.symbols','context.budget','context.dedup']
    return {cap:resolve_capability(root,cap) for cap in caps}

def build_context(index:dict[str,Any],task:str,budget:int=6000,session:str='default',max_files:int=12,max_symbols:int=20,include_content:bool=True,external_blocks:list[dict[str,Any]]|None=None)->dict[str,Any]:
    budget=max(800,budget); root=pathlib.Path(index['root']); terms=query_terms(task); providers=_provider_resolution(root)
    external_search=search_repository(root,'|'.join(terms[:6]) if terms else task,max_results=40) if terms else {'used':False,'results':[]}
    search_paths={r.get('path') for r in external_search.get('results',[]) if r.get('path')}
    ranked=rank_files(index.get('files',[]),index.get('graph',{'edges':{},'reverse':{},'degree':{}}),index.get('entry_points',[]),query=task)
    ranked=[{**f,'rank_score':round(float(f.get('rank_score',0))+(14.0 if f['path'] in search_paths else 0.0),3),'rank_reasons':list(f.get('rank_reasons',[]))+(['external-search-hit'] if f['path'] in search_paths else [])} for f in ranked]
    ranked.sort(key=lambda f:(-f['rank_score'],f['path']))
    ledger=SessionLedger(root,session=session); lifecycle=ContextLifecycle(root,session=session); used=0
    external_context=[]
    for block in deduplicate_blocks(external_blocks or []):
        est=int(block.get('estimated_tokens') or 0) or estimate_tokens_from_bytes(len(str(block).encode('utf-8')))
        if used+est>int(budget*0.45) and external_context: break
        fp=str(block.get('fingerprint') or _fingerprint(str(block))); key=f"external:{block.get('provider')}:{block.get('path')}:{block.get('symbol')}:{fp[:12]}"
        state=ledger.compare(key,fp,str(block.get('content') or ''))
        if state['state']=='unchanged': continue
        b={**block,'estimated_tokens':est,'context_id':key,'provenance':block.get('provenance') or {'provider':block.get('provider')}}; external_context.append(b); used+=est; ledger.record(key,fp,str(block.get('content') or '')); lifecycle.touch(key,fp,est)
    file_context=[]; file_candidates=ranked[:max(1,max_files*3)]; scored=[]
    for f in file_candidates:
        c=compact_file(f); est=estimate_tokens_from_bytes(len(str(c).encode('utf-8'))); rel=_normalized_relevance(float(f.get('rank_score',0))); voi=value_of_information(relevance=rel,uncertainty=1.0,novelty=1.0,graph_distance=None,estimated_tokens=est); scored.append((voi['score'],f,c,est,voi))
    scored.sort(key=lambda x:(-x[0],-float(x[1].get('rank_score',0)),x[1]['path']))
    for _,f,c,est,voi in scored:
        if len(file_context)>=max_files:break
        if used+est>int(budget*0.4) and file_context:break
        c.update({'estimated_tokens':est,'voi':voi,'context_id':f"file-structure:{f['path']}:{f.get('stat_fingerprint','')[:12]}",'provenance':{'provider':'repo-context-index','path':f['path'],'stat_fingerprint':f.get('stat_fingerprint')}}); file_context.append(c); used+=est; lifecycle.touch(c['context_id'],f.get('stat_fingerprint') or c['context_id'],est)
    candidates=[]; selected_paths={f['path'] for f in ranked[:max(1,max_files*2)]}
    for f in ranked:
        if f['path'] not in selected_paths:continue
        for sym in f.get('symbol_details',[]):
            raw_score=_symbol_score(sym,float(f.get('rank_score',0)),terms); estimated=max(20,int(max(1,int(sym.get('end_line',1))-int(sym.get('start_line',1))+1)*8)); rel=_normalized_relevance(raw_score); voi=value_of_information(relevance=rel,uncertainty=1.0,novelty=1.0,graph_distance=None,estimated_tokens=estimated); candidates.append({'path':f['path'],**sym,'selection_score':round(raw_score,3),'voi':voi})
    candidates.sort(key=lambda s:(-float(s['voi']['score']),-s['selection_score'],s['path'],s['name']))
    symbol_context=[]; skipped_seen=[]
    for sym in candidates[:max_symbols*4]:
        if len(symbol_context)>=max_symbols:break
        if sym['selection_score']<=0 and terms and symbol_context:continue
        record={k:sym[k] for k in ('path','name','kind','signature','start_line','end_line','selection_score','voi') if k in sym}
        if not include_content:
            est=estimate_tokens_from_bytes(len(str(record).encode('utf-8')))
            if used+est>budget:break
            record.update({'estimated_tokens':est,'content_mode':'structure-only','context_id':f"symbol-structure:{sym['path']}:{sym['name']}:{sym.get('start_line')}"}); symbol_context.append(record); used+=est; continue
        content,reason=_read_record(root,sym)
        if content is None: record['content_unavailable']=reason; continue
        fp=_fingerprint(content); key=f"symbol:{sym['path']}:{sym['name']}:{sym.get('start_line')}"; state=ledger.compare(key,fp,content)
        if state['state']=='unchanged':
            skipped_seen.append({'path':sym['path'],'symbol':sym['name']}); ref_est=estimate_tokens_from_bytes(len((sym['path']+sym['name']+sym.get('signature','')).encode('utf-8')))
            if used+ref_est<=budget: record.update({'content_mode':'reference-only-unchanged','already_seen':True,'estimated_tokens':ref_est,'fingerprint':fp,'context_id':key,'provenance':{'provider':'session-ledger','path':sym['path'],'symbol':sym['name'],'fingerprint':fp}}); symbol_context.append(record); used+=ref_est
            continue
        payload=content; mode='full-symbol'
        if state['state']=='changed' and state.get('diff') and len(state['diff'].encode('utf-8'))<len(content.encode('utf-8')): payload=state['diff']; mode='delta'
        est=estimate_tokens_from_bytes(len(payload.encode('utf-8')))
        if used+est>budget:continue
        record.update({'content':payload,'content_mode':mode,'fingerprint':fp,'estimated_tokens':est,'context_id':key,'provenance':{'provider':'repo-context-native-symbol-reader','path':sym['path'],'symbol':sym['name'],'fingerprint':fp}}); symbol_context.append(record); used+=est; ledger.record(key,fp,content); lifecycle.touch(key,fp,est)
    ledger.save(); lifecycle_counts=lifecycle.classify(); lifecycle.save()
    searchable=' '.join([f['path']+' '+' '.join(f.get('functions',[])+f.get('classes',[])+f.get('types',[])+f.get('routes',[])) for f in file_context]+[s['path']+' '+s['name']+' '+s.get('signature','') for s in symbol_context]+[str(b.get('path') or '')+' '+str(b.get('symbol') or '')+' '+str(b.get('content') or '')[:300] for b in external_context])
    coverage=_coverage(terms,searchable); stop=bool(coverage['score'] is not None and coverage['score']>=0.75 and (symbol_context or external_context))
    return {'task':task,'strategy':'provider-aware-progressive-budgeted','providers':providers,'external_search':{'used':external_search.get('used',False),'provider':(external_search.get('resolution') or {}).get('selected'),'result_count':len(external_search.get('results',[]))},'budget':{'requested_tokens':budget,'estimated_used_tokens':used,'estimate':'utf8-bytes/4','billing_guarantee':False},'external_context':external_context,'files':file_context,'symbols':symbol_context,'session_dedup':{'session':session,'unchanged_symbols_omitted':skipped_seen},'lifecycle':{'session':session,'tiers':lifecycle_counts,'runtime_eviction_guarantee':False},'coverage':coverage,'stop_condition':{'recommend_stop_expansion':stop,'classification':'heuristic','rule':'lexical coverage >= 0.75 and evidence selected'},'graph':{'selected_paths':[f['path'] for f in file_context],'dependency_edges':[{'from':f['path'],'to':dep,'confidence':'high','relation':'resolved-static-import','provenance':{'provider':'repo-context-native-graph'}} for f in ranked[:max_files] for dep in index.get('graph',{}).get('edges',{}).get(f['path'],[]) if dep in selected_paths][:40]},'notes':['Context was selected before reasoning; relevance/VoI/coverage/stop are heuristics, not model-understanding claims.','Static import and parsed symbol facts are deterministic where the parser resolved them.']}
