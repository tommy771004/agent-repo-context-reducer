from __future__ import annotations

import contextlib
import io
import json
import pathlib
import tempfile
import unittest

from repo_context.cli import main
from repo_context.grader import build_grade_packet, evaluate_grade
from repo_context.lane_budget import allocate_lane_budgets
from repo_context.model_router import route_models
from repo_context.orchestration import plan_harness
from repo_context.retry_policy import decide_retry
from repo_context.risk import classify_risk
from repo_context.scheduler import build_schedule
from repo_context.task_budget import BudgetLimits, TaskBudget


class V13RoutingTests(unittest.TestCase):
    def test_deterministic_sorter_uses_zero_model_calls(self):
        result = route_models("Explain this function")
        self.assertEqual(result["sorter_policy"]["primary"], "deterministic")
        self.assertEqual(result["sorter_policy"]["model_calls"], 0)
        self.assertNotIn("sorter", result["roles"])

    def test_high_risk_payment_migration_requires_strong_grader(self):
        result = route_models("Migrate the production payment database schema across the repo", "change-impact")
        self.assertIn(result["risk"]["level"], {"high", "critical"})
        self.assertEqual(result["roles"]["grader"], "strong")
        self.assertEqual(result["roles"]["planner"], "strong")

    def test_ambiguity_escalates_small_worker_beyond_cheap(self):
        result = route_models("Login randomly fails sometimes", "debug")
        self.assertTrue(result["risk"]["requires_escalation"])
        self.assertIn(result["roles"]["worker"], {"standard", "strong"})

    def test_model_tiers_stay_vendor_neutral_and_unresolved_without_provider(self):
        with tempfile.TemporaryDirectory() as td:
            result = route_models("Implement a payment migration across the repo", "debug", repo=td)
            self.assertTrue(result["vendor_neutral"])
            for resolution in result["provider_resolution"].values():
                self.assertIsNone(resolution["selected"])

    def test_lane_budget_never_exceeds_aggregate(self):
        task = "Refactor authentication and migrate database integration across the repo"
        schedule = build_schedule(task, "debug")
        models = route_models(task, "debug")
        result = allocate_lane_budgets(schedule, models, context_tokens=6000, output_tokens=2000, model_calls=10)
        self.assertEqual(result["allocated"]["context_tokens"], 6000)
        self.assertEqual(result["allocated"]["output_tokens"], 2000)
        self.assertLessEqual(result["allocated"]["base_model_calls"], 10)

    def test_task_budget_enforces_lane_and_aggregate_together(self):
        with tempfile.TemporaryDirectory() as td:
            budget = TaskBudget(pathlib.Path(td), "r", BudgetLimits(context_tokens=1000, output_tokens=500, model_calls=3))
            budget.configure_lanes([{"id": "work", "context_tokens": 600, "output_tokens": 300, "model_calls": 1}])
            state = budget.consume_lane("work", context_tokens=600, model_calls=1)
            self.assertFalse(state["lane"]["allow_more_work"])
            self.assertEqual(state["used"]["context_tokens"], 600)
            self.assertEqual(state["used"]["model_calls"], 1)

    def test_quality_gate_uses_reduced_worker_payload(self):
        packet = build_grade_packet(
            "Review payment change",
            {"summary": "changed", "tests": ["ok"], "debug_log": "x" * 10000},
            task_type="review",
        )
        reduced = packet["reduced_worker_handoff"]["handoff"]
        self.assertNotIn("debug_log", reduced)
        self.assertIn("tests", reduced)

    def test_high_risk_grade_requires_higher_threshold(self):
        result = evaluate_grade({"decision": "pass", "score": 0.85, "failures": []}, risk_level="high")
        self.assertEqual(result["decision"], "uncertain")
        self.assertTrue(result["requires_escalation"])

    def test_retry_loop_is_bounded_and_escalates_tier(self):
        first = decide_retry(decision="reject", attempt=1, worker_tier="standard", risk_level="high", complexity_level="complex")
        self.assertEqual(first["action"], "retry")
        self.assertEqual(first["next_tier"], "strong")
        second = decide_retry(decision="reject", attempt=2, worker_tier="strong", risk_level="high", complexity_level="complex")
        self.assertEqual(second["action"], "human-review")

    def test_scheduler_has_independent_grade_gate(self):
        result = build_schedule("Refactor payment integration across the repo", "debug")
        nodes = {n["id"]: n for n in result["nodes"]}
        self.assertIn("grade", nodes)
        self.assertEqual(nodes["grade"]["role"], "grader")
        self.assertIn("test", nodes["grade"]["depends_on"])

    def test_harness_plan_contains_risk_model_lane_grade_retry(self):
        with tempfile.TemporaryDirectory() as td:
            result = plan_harness("Migrate production payment database across the repo", td, forced_type="change-impact", context_tokens=6000)
            self.assertIn("risk", result)
            self.assertIn("model_policy", result)
            self.assertIn("lane_budget", result)
            self.assertIn("quality_gate", result)
            self.assertIn("retry_policy", result)
            self.assertIsNone(result["provider_layers"]["model"]["model.strong"])

    def test_context_facade_exposes_integrated_routing_policy(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["run", "reducer-debug", "login randomly fails sometimes", "--repo", td, "--budget", "1200"])
            self.assertEqual(rc, 0)
            data = json.loads(out.getvalue())
            orchestration = data["orchestration"]
            self.assertEqual(orchestration["route"]["task_type"], "debug")
            self.assertIn("model_policy", orchestration)
            self.assertIn("lane_budget", orchestration)
            self.assertIn("quality_gate", orchestration)

    def test_cli_quality_packet_and_retry_decision(self):
        with tempfile.TemporaryDirectory() as td:
            payload = pathlib.Path(td) / "worker.json"
            payload.write_text(json.dumps({"summary": "done", "tests": ["pass"]}), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["quality", "packet", "review payment change", str(payload), "--intent", "review"])
            self.assertEqual(rc, 0)
            packet = json.loads(out.getvalue())
            self.assertEqual(packet["schema"], "repo-context-grade-packet/v1")

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["retry-decision", "reject", "--attempt", "1", "--worker-tier", "standard",
                           "--risk-level", "high", "--complexity-level", "complex"])
            self.assertEqual(rc, 0)
            retry = json.loads(out.getvalue())
            self.assertEqual(retry["action"], "retry")
            self.assertEqual(retry["next_tier"], "strong")


if __name__ == "__main__":
    unittest.main()
