from __future__ import annotations
import contextlib, io, json, pathlib, tempfile, unittest
from repo_context.cli import main
from repo_context.grader import build_grade_packet,evaluate_grade
from repo_context.lane_budget import allocate_lane_budgets
from repo_context.model_router import route_models
from repo_context.orchestration import plan_harness
from repo_context.retry_policy import decide_retry
from repo_context.scheduler import build_schedule
from repo_context.task_budget import BudgetLimits,TaskBudget
class V13Tests(unittest.TestCase):
    def test_deterministic_sorter(self): self.assertEqual(route_models('Explain this function')['sorter_policy']['model_calls'],0)
    def test_high_risk_strong_grader(self): self.assertEqual(route_models('Migrate the production payment database schema across the repo','change-impact')['roles']['grader'],'strong')
    def test_model_tiers_unresolved(self):
        with tempfile.TemporaryDirectory() as td:
            for r in route_models('Implement a payment migration across the repo','debug',repo=td)['provider_resolution'].values(): self.assertIsNone(r['selected'])
    def test_lane_budget(self):
        task='Refactor authentication and migrate database integration across the repo'; sch=build_schedule(task,'debug'); models=route_models(task,'debug'); r=allocate_lane_budgets(sch,models,context_tokens=6000,output_tokens=2000,model_calls=10); self.assertEqual(r['allocated']['context_tokens'],6000)
    def test_task_budget_lane(self):
        with tempfile.TemporaryDirectory() as td:
            b=TaskBudget(pathlib.Path(td),'r',BudgetLimits(context_tokens=1000,output_tokens=500,model_calls=3)); b.configure_lanes([{'id':'work','context_tokens':600,'output_tokens':300,'model_calls':1}]); self.assertFalse(b.consume_lane('work',context_tokens=600,model_calls=1)['lane']['allow_more_work'])
    def test_quality_packet(self): self.assertNotIn('debug_log',build_grade_packet('Review payment change',{'summary':'changed','tests':['ok'],'debug_log':'x'*10000},task_type='review')['reduced_worker_handoff']['handoff'])
    def test_retry_bounded(self): self.assertEqual(decide_retry(decision='reject',attempt=2,worker_tier='strong',risk_level='high',complexity_level='complex')['action'],'human-review')
    def test_harness_plan(self):
        with tempfile.TemporaryDirectory() as td:
            r=plan_harness('Migrate production payment database across the repo',td,forced_type='change-impact',context_tokens=6000); self.assertIn('lane_budget',r); self.assertIsNone(r['provider_layers']['model']['model.strong'])
    def test_cli_quality_and_retry(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/'w.json'; p.write_text(json.dumps({'summary':'done','tests':['pass']})); out=io.StringIO()
            with contextlib.redirect_stdout(out): rc=main(['quality','packet','review payment change',str(p),'--intent','review'])
            self.assertEqual(rc,0); self.assertEqual(json.loads(out.getvalue())['schema'],'repo-context-grade-packet/v1')
if __name__=='__main__': unittest.main()
