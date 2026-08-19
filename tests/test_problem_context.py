from __future__ import annotations

import pathlib
import tempfile
import unittest

from repo_context.context_planner import build_context
from repo_context.context_safety import assess_context_sufficiency
from repo_context.capabilities import CORE_CAPABILITIES, NATIVE_CAPABILITIES
from repo_context.model_context import split_model_context
from repo_context.problem_context import (
    build_problem_plan,
    build_workflow_plan,
    derive_problem_requirements,
    derive_workflow_dimensions,
    finalize_problem_plan,
)
from repo_context.scanner import build_index


class ProblemRequirementTests(unittest.TestCase):
    def test_problem_preserving_dedup_is_a_core_capability(self):
        self.assertIn("context.problem-preserving-dedup", NATIVE_CAPABILITIES)
        self.assertIn("context.problem-preserving-dedup", CORE_CAPABILITIES)
        self.assertIn("context.workflow-recall", NATIVE_CAPABILITIES)
        self.assertIn("context.workflow-recall", CORE_CAPABILITIES)

    def test_explicit_problem_list_is_never_collapsed(self):
        requirements = derive_problem_requirements(
            "請處理以下問題：\n1. 登入失敗\n2. 手機版 header 遮擋\n3. 動畫需支援 reduced motion"
        )
        self.assertEqual([item["id"] for item in requirements], ["problem-001", "problem-002", "problem-003"])
        self.assertEqual(len(requirements), 3)

    def test_list_preamble_is_inherited_for_ranking_but_not_problem_identity(self):
        requirements = derive_problem_requirements("UI/UX 改善：\n1. 修復 header\n2. 改善動畫")
        self.assertEqual([item["text"] for item in requirements], ["修復 header", "改善動畫"])
        self.assertTrue(all("UI/UX" in item["query"] for item in requirements))

    def test_compact_chinese_problem_list_inherits_action(self):
        requirements = derive_problem_requirements("修復登入、RWD、動畫問題")
        self.assertEqual(len(requirements), 3)
        self.assertTrue(all(item["text"].startswith("修復") for item in requirements))

    def test_workflow_analysis_selects_compact_dimension_ledger(self):
        dimensions = derive_workflow_dimensions("分析整個 workflow 問題與使用者流程功能缺口")
        ids = {item["id"] for item in dimensions}
        self.assertIn("auth-and-authorization", ids)
        self.assertIn("cross-layer-contract", ids)
        self.assertIn("error-and-retry", ids)
        self.assertLessEqual(sum(len(item["terms"]) for item in dimensions), 70)


class ProblemContextPlanningTests(unittest.TestCase):
    def test_workflow_dimensions_are_retained_and_bound_once(self):
        files = [
            {"path": "src/App.tsx", "functions": ["login", "saveTrip"], "imports": [], "symbol_details": []},
            {"path": "server.ts", "functions": ["registerRoute"], "imports": [], "symbol_details": []},
        ]
        workflow = build_workflow_plan("分析整個 workflow 問題與使用者流程功能缺口", files, {"edges": {}, "reverse": {}, "degree": {}}, [])
        self.assertEqual(workflow["contract_pairs"], [{"client_path": "src/App.tsx", "server_path": "server.ts"}])
        plan = build_problem_plan("分析整個 workflow 問題", files, {"edges": {}, "reverse": {}, "degree": {}}, [])
        result = finalize_problem_plan(
            plan,
            [{
                "context_id": "file:src/App.tsx:abc",
                "path": "src/App.tsx",
                "problem_ids": ["problem-001"],
                "workflow_dimension_ids": [item["id"] for item in workflow["dimensions"]],
                "estimated_tokens": 80,
            }, {
                "context_id": "file:server.ts:def",
                "path": "server.ts",
                "problem_ids": [],
                "workflow_dimension_ids": ["cross-layer-contract"],
                "estimated_tokens": 80,
            }],
            batch_budget=100,
            workflow_plan=workflow,
        )
        self.assertTrue(result["summary"]["all_workflow_dimensions_covered"])
        self.assertEqual(result["summary"]["workflow_queued_count"], 0)
        self.assertEqual(len(result["context_catalog"]), 2)
    def test_shared_context_is_catalogued_once_and_referenced_by_each_problem(self):
        files = [
            {"path": "src/App.tsx", "functions": ["login", "renderMobile"], "imports": [], "symbol_details": []},
            {"path": "src/store.ts", "functions": ["persistSession"], "imports": [], "symbol_details": []},
        ]
        plan = build_problem_plan(
            "1. fix login layout\n2. fix mobile layout",
            files,
            {"edges": {}, "reverse": {}, "degree": {}},
            [],
        )
        problem_ids = [item["id"] for item in plan["requirements"]]
        result = finalize_problem_plan(
            plan,
            [{
                "context_id": "file:src/App.tsx:abc",
                "path": "src/App.tsx",
                "problem_ids": problem_ids,
                "content_mode": "full-symbol",
                "estimated_tokens": 80,
            }],
            batch_budget=100,
        )
        self.assertEqual(result["summary"]["problem_retention_rate"], 1.0)
        self.assertEqual(result["summary"]["unique_context_count"], 1)
        self.assertEqual(result["summary"]["context_reference_count"], 2)
        self.assertEqual(result["summary"]["duplicate_context_references_avoided"], 1)
        self.assertTrue(result["summary"]["all_problems_covered"])
        self.assertEqual(sum(len(batch["context_ids"]) for batch in result["batches"]), 1)

    def test_budget_overflow_keeps_problem_and_context_identity(self):
        plan = build_problem_plan(
            "- fix login",
            [{"path": "auth.py", "functions": ["login"], "imports": [], "symbol_details": []}],
            {"edges": {}, "reverse": {}, "degree": {}},
            [],
        )
        result = finalize_problem_plan(
            plan,
            [{
                "context_id": "symbol:auth.py:login:1",
                "path": "auth.py",
                "name": "login",
                "problem_ids": ["problem-001"],
                "estimated_tokens": 500,
            }],
            batch_budget=100,
        )
        self.assertEqual(result["requirements"][0]["status"], "covered")
        self.assertEqual(result["batches"][0]["problem_ids"], ["problem-001"])
        self.assertEqual(result["batches"][0]["context_ids"], ["symbol:auth.py:login:1"])
        self.assertTrue(result["batches"][0]["overflow"])


class ProblemContextIntegrationTests(unittest.TestCase):
    def test_context_retains_every_problem_when_hot_budget_cannot_cover_every_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "auth.py").write_text("def login():\n    return 'token'\n", encoding="utf-8")
            (root / "responsive.tsx").write_text("export function MobileLayout(){ return <main /> }\n", encoding="utf-8")
            (root / "storage.py").write_text("def persist_state():\n    return True\n", encoding="utf-8")
            task = "1. fix login token\n2. fix mobile layout\n3. fix persisted state"
            context = build_context(build_index(root), task, budget=900, max_files=2, max_symbols=2)
            problem_context = context["problem_context"]
            self.assertEqual(problem_context["summary"]["problem_count"], 3)
            self.assertEqual(problem_context["summary"]["problem_retention_rate"], 1.0)
            self.assertEqual(problem_context["summary"]["queued_problem_count"], len(problem_context["recall_queue"]))
            batched_ids = [problem_id for batch in problem_context["batches"] for problem_id in batch["problem_ids"]]
            self.assertEqual(batched_ids, ["problem-001", "problem-002", "problem-003"])

            model = split_model_context(context)["model_payload"]
            self.assertEqual(len(model["problem_context"]["requirements"]), 3)
            context_ids = [item["context_id"] for item in model["problem_context"]["context_catalog"]]
            self.assertEqual(len(context_ids), len(set(context_ids)))
            self.assertEqual(model["policy"]["output_policy"]["style"], "compact-evidence-first")
            self.assertTrue(model["policy"]["output_policy"]["unresolved_items_required"])

    def test_sufficiency_fails_when_any_problem_is_only_queued(self):
        status = assess_context_sufficiency({
            "files": [{"path": "auth.py"}],
            "symbols": [],
            "external_context": [],
            "coverage": {"score": 1.0},
            "problem_context": {
                "requirements": [
                    {"id": "problem-001", "status": "covered"},
                    {"id": "problem-002", "status": "queued"},
                ],
                "summary": {"all_problems_covered": False},
            },
        })
        self.assertFalse(status["sufficient"])
        self.assertIn("problem-evidence-incomplete", status["reasons"])

    def test_sufficiency_fails_when_workflow_dimension_is_queued(self):
        status = assess_context_sufficiency({
            "files": [{"path": "src/App.tsx"}],
            "symbols": [],
            "external_context": [],
            "coverage": {"score": 1.0},
            "problem_context": {
                "requirements": [{"id": "problem-001", "status": "covered"}],
                "workflow": {"dimensions": [{"id": "cross-layer-contract", "status": "queued"}]},
            },
        })
        self.assertFalse(status["sufficient"])
        self.assertIn("workflow-dimension-evidence-incomplete", status["reasons"])


if __name__ == "__main__":
    unittest.main()
