from __future__ import annotations
import json, pathlib, sys, tempfile, unittest
from repo_context.attribution import analyze_context_usage
from repo_context.artifact_store import ArtifactStore
from repo_context.benchmark import benchmark_tasks
from repo_context.capabilities import detect_providers, resolve_capability, doctor
from repo_context.external_context import canonicalize_external, deduplicate_blocks
from repo_context.delegate import delegate_capability
from repo_context.config import trust_provider
from repo_context.provider_health import ProviderHealth
from repo_context.fanout import recommend_fanout
from repo_context.lifecycle import ContextLifecycle
from repo_context.handoff import reduce_handoff
from repo_context.knowledge import build_knowledge_index, search_knowledge
from repo_context.orchestration import plan_harness
from repo_context.scheduler import build_schedule
from repo_context.task_budget import BudgetLimits, TaskBudget
from repo_context.tool_policy import classify_command
from repo_context.trace import Trace, replay_summary
from repo_context.voi import value_of_information

class HarnessTests(unittest.TestCase):
    def test_detect_skill_overlap_without_auto_delegation(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); skill=root/'.agents/skills/graph-guru'; skill.mkdir(parents=True); (skill/'SKILL.md').write_text('---\nname: graph-guru\ndescription: Builds a code graph and symbol index.\n---\n')
            d=detect_providers(root,required=['repository.graph'],use_cache=False); self.assertTrue(any(p['id']=='skill:graph-guru' for p in d['providers'])); self.assertEqual(resolve_capability(root,'repository.graph')['selected']['source_type'],'native')
    def test_manifest_requires_authorization(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); skill=root/'.agents/skills/graph-guru'; skill.mkdir(parents=True); (skill/'SKILL.md').write_text('---\nname: graph-guru\ndescription: graph\n---\n'); (skill/'capabilities.json').write_text(json.dumps({'schema':'repo-context-capabilities/v1','provides':[{'capability':'repository.graph','command':{'argv':[sys.executable,'-c','print("{}")']}}]}))
            self.assertEqual(resolve_capability(root,'repository.graph')['selected']['source_type'],'native'); self.assertEqual(resolve_capability(root,'repository.graph',allow_external_commands=True)['selected']['id'],'skill:graph-guru')
    def test_trusted_manifest_reused(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); skill=root/'.agents/skills/graph-guru'; skill.mkdir(parents=True); (skill/'SKILL.md').write_text('---\nname: graph-guru\ndescription: graph\n---\n'); (skill/'capabilities.json').write_text(json.dumps({'schema':'repo-context-capabilities/v1','provides':[{'capability':'repository.graph','command':{'argv':[sys.executable,'-c','print("{}")']}}]})); trust_provider(root,'skill:graph-guru',True); self.assertEqual(resolve_capability(root,'repository.graph')['selected']['id'],'skill:graph-guru')
    def test_external_context_exact_dedup(self):
        b=canonicalize_external('p1',[{'path':'a.py','symbol':'run','content':'def run(): pass'},{'path':'a.py','symbol':'run','content':'def run(): pass'}]); self.assertEqual(len(deduplicate_blocks(b)),1)
    def test_task_budget_blocks(self):
        with tempfile.TemporaryDirectory() as td: self.assertFalse(TaskBudget(pathlib.Path(td),'run',BudgetLimits(context_tokens=100)).consume(context_tokens=100)['allow_more_work'])
    def test_lifecycle_demotes(self):
        with tempfile.TemporaryDirectory() as td:
            life=ContextLifecycle(pathlib.Path(td),'s'); life.touch('a','x',5000); life.touch('b','y',5000); self.assertTrue(life.evict(max_hot_tokens=5000)['demoted_to_warm'])
    def test_tool_policy(self): self.assertEqual(classify_command('git reset --hard HEAD~1')['risk'],'destructive')
    def test_fanout(self): self.assertEqual(recommend_fanout(.92,2,2,4)['recommended_new_subagents'],0)
    def test_voi(self): self.assertGreater(value_of_information(relevance=1,uncertainty=1,novelty=1,graph_distance=0,estimated_tokens=100)['score'],value_of_information(relevance=1,uncertainty=1,novelty=1,graph_distance=0,estimated_tokens=10000)['score'])
    def test_trace(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); t=Trace(root,'r1'); t.event('route',{'task':'debug'}); self.assertEqual(replay_summary(root,'r1')['counts']['route'],1)
    def test_attribution(self): self.assertEqual(analyze_context_usage({'files':[{'path':'a.py','functions':['run'],'classes':[],'types':[],'estimated_tokens':100}],'symbols':[]},'run is relevant')['classification'],'heuristic-lexical-attribution')
    def test_benchmark_recall(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); (root/'payment.py').write_text('def charge(amount):\n return amount\n'); self.assertEqual(benchmark_tasks(root,[{'task':'payment charge','expected_paths':['payment.py']}],budget=1200)['tasks'][0]['expected_path_recall'],1.0)
    def test_artifact_store(self):
        with tempfile.TemporaryDirectory() as td:
            store=ArtifactStore(td); item=store.put({'summary':'x','raw':'y'*5000},producer='researcher'); self.assertNotIn('payload',item); self.assertEqual(store.get(item['id'])['payload']['summary'],'x')
    def test_handoff_reducer(self): self.assertNotIn('debug_log',reduce_handoff({'summary':'done','debug_log':'x'*10000},from_role='planner',to_role='implementer')['handoff'])
    def test_scheduler(self):
        r=build_schedule('Refactor authentication and migrate database integration across the repo','debug'); nodes={n['id']:set(n['depends_on']) for n in r['nodes']}; self.assertTrue(all(not(nodes[n]&set(w)) for w in r['waves'] for n in w))
    def test_knowledge(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); (root/'docs').mkdir(); (root/'docs/adr.md').write_text('# Payment\nUse event queue.'); build_knowledge_index(root); self.assertEqual(search_knowledge(root,'payment queue')['results'][0]['path'],'docs/adr.md')
    def test_executor_unresolved(self):
        with tempfile.TemporaryDirectory() as td: self.assertIsNone(resolve_capability(pathlib.Path(td),'executor.autonomous')['selected'])
    def test_plan_executor_optional(self):
        with tempfile.TemporaryDirectory() as td:
            r=plan_harness('Autonomously implement an end-to-end migration across the entire project and ship production-ready integration',td); self.assertIn('executor.autonomous',r['capability_plan']['optional'])
if __name__=='__main__': unittest.main()
