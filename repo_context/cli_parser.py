from __future__ import annotations
import argparse
from . import __version__
from .command_facade import FACADES

def _add_common(p):
    p.add_argument('path',nargs='?',default='.')
    p.add_argument('--max-files',type=int,default=10000); p.add_argument('--max-file-bytes',type=int,default=512_000)
    p.add_argument('--include-hidden',action='store_true'); p.add_argument('--include-generated',action='store_true')
    p.add_argument('--no-cache',action='store_true'); p.add_argument('--no-sync',action='store_true'); p.add_argument('--pretty',action='store_true')

def build_parser():
    parser=argparse.ArgumentParser(prog='repo-context',description='Provider-aware repository context harness for AI coding agents.')
    parser.add_argument('--version',action='version',version=f'repo-context {__version__}')
    sub=parser.add_subparsers(dest='command',required=True)
    for name,helptext in [('index','Build/rebuild native persistent repository index'),('sync','Refresh persistent index')]:
        p=sub.add_parser(name,help=helptext); _add_common(p)
    p=sub.add_parser('status'); p.add_argument('path',nargs='?',default='.'); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('detect'); p.add_argument('path',nargs='?',default='.'); p.add_argument('--capability',action='append',default=[]); p.add_argument('--no-cache',action='store_true'); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('doctor'); p.add_argument('path',nargs='?',default='.'); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('resolve'); p.add_argument('capability'); p.add_argument('path',nargs='?',default='.'); p.add_argument('--allow-external-commands',action='store_true'); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('delegate'); p.add_argument('capability'); p.add_argument('task'); p.add_argument('path',nargs='?',default='.'); p.add_argument('--allow-external-commands',action='store_true'); p.add_argument('--timeout',type=int,default=30); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('provider-health'); p.add_argument('path',nargs='?',default='.'); p.add_argument('--provider'); p.add_argument('--pretty',action='store_true')
    for n in ('provider-trust','provider-untrust'):
        p=sub.add_parser(n); p.add_argument('provider_id'); p.add_argument('path',nargs='?',default='.'); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('provider-prefer'); p.add_argument('capability'); p.add_argument('provider_id'); p.add_argument('path',nargs='?',default='.'); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('provider-config'); p.add_argument('path',nargs='?',default='.'); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('route'); p.add_argument('task'); p.add_argument('--repo',default='.'); p.add_argument('--no-resolve',action='store_true'); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('context'); _add_common(p); p.add_argument('task'); p.add_argument('--budget',type=int,default=6000); p.add_argument('--session',default='default'); p.add_argument('--run-id'); p.add_argument('--max-context-files',type=int,default=12); p.add_argument('--max-symbols',type=int,default=20); p.add_argument('--structure-only',action='store_true'); p.add_argument('--external-only',action='store_true'); p.add_argument('--external',action='append',default=[]); p.add_argument('--intent',choices=['understand','debug','change-impact','review'])
    p=sub.add_parser('run'); p.add_argument('facade',choices=list(FACADES)); p.add_argument('task',nargs='?',default=''); p.add_argument('--repo',default='.'); p.add_argument('--budget',type=int); p.add_argument('--session',default='default'); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('commands'); p.add_argument('--pretty',action='store_true')
    for n in ('host-install','host-status','host-uninstall'):
        p=sub.add_parser(n); p.add_argument('--host',required=True,choices=['claude-code','codex']); p.add_argument('--scope',choices=['project','global'],default='project'); p.add_argument('--repo',default='.'); p.add_argument('--pretty',action='store_true')
        if n=='host-install': p.add_argument('--dry-run',action='store_true')
        if n=='host-uninstall': p.add_argument('--yes',action='store_true'); p.add_argument('--force',action='store_true')
    p=sub.add_parser('complexity'); p.add_argument('task'); p.add_argument('--intent',choices=['understand','debug','change-impact','review']); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('plan'); p.add_argument('task'); p.add_argument('--repo',default='.'); p.add_argument('--intent',choices=['understand','debug','change-impact','review']); p.add_argument('--context-budget',type=int,default=12000); p.add_argument('--output-budget',type=int,default=4000); p.add_argument('--model-calls',type=int,default=10); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('schedule'); p.add_argument('task'); p.add_argument('--intent',choices=['understand','debug','change-impact','review']); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('handoff'); p.add_argument('from_role'); p.add_argument('to_role'); p.add_argument('input'); p.add_argument('--repo',default='.'); p.add_argument('--task',default=''); p.add_argument('--store-artifact',action='store_true'); p.add_argument('--token-budget',type=int); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('ingest'); p.add_argument('provider'); p.add_argument('json_file'); p.add_argument('--pretty',action='store_true')
    for n in ('map','scan'):
        p=sub.add_parser(n); _add_common(p); p.add_argument('--top-k',type=int,default=25); p.add_argument('--query')
    p=sub.add_parser('query'); _add_common(p); p.add_argument('query'); p.add_argument('--top-k',type=int,default=20)
    p=sub.add_parser('module'); _add_common(p); p.add_argument('module'); p.add_argument('--top-k',type=int,default=30); p.add_argument('--query')
    p=sub.add_parser('deps'); _add_common(p); p.add_argument('file'); p.add_argument('--depth',type=int,default=1)
    p=sub.add_parser('callers'); _add_common(p); p.add_argument('file')
    p=sub.add_parser('impact'); _add_common(p); p.add_argument('file'); p.add_argument('--depth',type=int,default=2); p.add_argument('--top-k',type=int,default=40)
    p=sub.add_parser('changed'); _add_common(p); p.add_argument('--base'); p.add_argument('--depth',type=int,default=1); p.add_argument('--top-k',type=int,default=40)
    p=sub.add_parser('symbol'); p.add_argument('path'); p.add_argument('file'); p.add_argument('symbol'); p.add_argument('--session',default='default'); p.add_argument('--max-file-bytes',type=int,default=2_000_000); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('admit'); _add_common(p); p.add_argument('file'); p.add_argument('task'); p.add_argument('--session',default='default'); p.add_argument('--requested',choices=['full','structure','symbol'],default='full')
    p=sub.add_parser('inspect'); p.add_argument('path'); p.add_argument('--max-file-bytes',type=int,default=1_000_000); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('tool-policy'); p.add_argument('command_line'); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('fanout'); p.add_argument('--coverage',type=float); p.add_argument('--unresolved',type=int,default=1); p.add_argument('--used-subagents',type=int,default=0); p.add_argument('--max-subagents',type=int,default=4); p.add_argument('--concurrency',type=int,default=2); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('benchmark'); p.add_argument('tasks_json'); p.add_argument('path',nargs='?',default='.'); p.add_argument('--budget',type=int,default=6000); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('replay'); p.add_argument('run_id'); p.add_argument('path',nargs='?',default='.'); p.add_argument('--pretty',action='store_true')

    p=sub.add_parser('quality'); p.add_argument('action',choices=['packet','evaluate']); p.add_argument('value'); p.add_argument('input',nargs='?'); p.add_argument('--intent',choices=['understand','debug','change-impact','review']); p.add_argument('--artifact-id'); p.add_argument('--risk-level',choices=['low','medium','high','critical']); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('retry-decision'); p.add_argument('decision',choices=['pass','reject','uncertain']); p.add_argument('--attempt',type=int,required=True); p.add_argument('--worker-tier',choices=['cheap','standard','strong'],required=True); p.add_argument('--risk-level',choices=['low','medium','high','critical'],required=True); p.add_argument('--complexity-level',choices=['trivial','focused','complex','autonomous'],required=True); p.add_argument('--force-escalation',action='store_true'); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('artifact'); p.add_argument('action',choices=['put','get','list','remove']); p.add_argument('value',nargs='?'); p.add_argument('--repo',default='.'); p.add_argument('--kind',default='agent-output'); p.add_argument('--producer',default='unknown'); p.add_argument('--payload',action='store_true'); p.add_argument('--limit',type=int,default=50); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('knowledge'); p.add_argument('action',choices=['index','search','status']); p.add_argument('query',nargs='?'); p.add_argument('--repo',default='.'); p.add_argument('--top-k',type=int,default=8); p.add_argument('--budget',type=int,default=1800); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('update'); p.add_argument('--repo',default='.'); p.add_argument('--target',choices=['all','index','shortcuts','self'],default='all'); p.add_argument('--host',action='append',choices=['claude-code','codex'],default=[]); p.add_argument('--scope',action='append',choices=['project','global'],default=[]); p.add_argument('--dry-run',action='store_true'); p.add_argument('--max-files',type=int,default=10000); p.add_argument('--max-file-bytes',type=int,default=512_000); p.add_argument('--include-hidden',action='store_true'); p.add_argument('--include-generated',action='store_true'); p.add_argument('--no-cache',action='store_true'); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('remove'); p.add_argument('--repo',default='.'); p.add_argument('--target',choices=['state','shortcuts','artifacts','all'],default='state'); p.add_argument('--host',action='append',choices=['claude-code','codex'],default=[]); p.add_argument('--scope',action='append',choices=['project','global'],default=[]); p.add_argument('--yes',action='store_true'); p.add_argument('--all',dest='include_preserved',action='store_true'); p.add_argument('--force',action='store_true'); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('budget'); p.add_argument('action',choices=['init','status','consume']); p.add_argument('run_id'); p.add_argument('path',nargs='?',default='.'); p.add_argument('--context-tokens',type=int,default=0); p.add_argument('--output-tokens',type=int,default=0); p.add_argument('--tool-calls',type=int,default=0); p.add_argument('--model-calls',type=int,default=0); p.add_argument('--subagents',type=int,default=0); p.add_argument('--limit-context',type=int,default=12000); p.add_argument('--limit-output',type=int,default=4000); p.add_argument('--limit-tools',type=int,default=30); p.add_argument('--limit-models',type=int,default=10); p.add_argument('--limit-subagents',type=int,default=4); p.add_argument('--limit-wall',type=int,default=900); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('lifecycle'); p.add_argument('action',choices=['status','evict']); p.add_argument('path',nargs='?',default='.'); p.add_argument('--session',default='default'); p.add_argument('--max-hot-tokens',type=int,default=6000); p.add_argument('--pretty',action='store_true')
    p=sub.add_parser('analyze-context'); p.add_argument('context_json'); p.add_argument('answer_file'); p.add_argument('--pretty',action='store_true')
    return parser
