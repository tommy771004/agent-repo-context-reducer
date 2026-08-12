from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
import sys

from repo_context.attribution import analyze_context_usage
from repo_context.benchmark import benchmark_tasks
from repo_context.capabilities import detect_providers, resolve_capability, doctor
from repo_context.external_context import canonicalize_external, deduplicate_blocks
from repo_context.delegate import delegate_capability
from repo_context.config import trust_provider
from repo_context.provider_health import ProviderHealth
from repo_context.fanout import recommend_fanout
from repo_context.lifecycle import ContextLifecycle
from repo_context.task_budget import BudgetLimits, TaskBudget
from repo_context.tool_policy import classify_command
from repo_context.trace import Trace, replay_summary
from repo_context.voi import value_of_information


class HarnessTests(unittest.TestCase):
    def test_detect_skill_overlap_without_auto_delegation(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            skill = root / ".agents" / "skills" / "graph-guru"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: graph-guru\ndescription: Builds a code graph and symbol index.\n---\n", encoding="utf-8")
            detected = detect_providers(root, required=["repository.graph"], use_cache=False)
            ids = {p["id"] for p in detected["providers"]}
            self.assertIn("skill:graph-guru", ids)
            resolution = resolve_capability(root, "repository.graph")
            self.assertEqual(resolution["selected"]["source_type"], "native")
            self.assertTrue(resolution["potential_overlaps"])

    def test_manifest_provider_requires_external_command_authorization(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            skill = root / ".agents" / "skills" / "graph-guru"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: graph-guru\ndescription: graph\n---\n", encoding="utf-8")
            (skill / "capabilities.json").write_text(json.dumps({
                "schema": "repo-context-capabilities/v1",
                "provides": [{"capability": "repository.graph", "command": {"argv": ["graph-guru", "query"]}}]
            }), encoding="utf-8")
            blocked = resolve_capability(root, "repository.graph", allow_external_commands=False)
            self.assertEqual(blocked["selected"]["source_type"], "native")
            allowed = resolve_capability(root, "repository.graph", allow_external_commands=True)
            self.assertEqual(allowed["selected"]["id"], "skill:graph-guru")

    def test_doctor_reports_overlap(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            skill = root / ".agents" / "skills" / "repo-map"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: repo-map\ndescription: repository graph and symbol index\n---\n", encoding="utf-8")
            result = doctor(root)
            self.assertIn("repository.graph", result["overlaps"])

    def test_external_context_exact_dedup(self):
        blocks = canonicalize_external("p1", [
            {"path": "a.py", "symbol": "run", "content": "def run(): pass"},
            {"path": "a.py", "symbol": "run", "content": "def run(): pass"},
        ])
        self.assertEqual(len(deduplicate_blocks(blocks)), 1)

    def test_trusted_manifest_provider_is_reused_without_per_call_allow_flag(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            skill = root / ".agents" / "skills" / "graph-guru"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: graph-guru\ndescription: graph\n---\n", encoding="utf-8")
            (skill / "capabilities.json").write_text(json.dumps({
                "schema": "repo-context-capabilities/v1",
                "provides": [{"capability": "repository.graph", "command": {"argv": [sys.executable, "-c", "print('{}')"]}}]
            }), encoding="utf-8")
            before = resolve_capability(root, "repository.graph")
            self.assertEqual(before["selected"]["source_type"], "native")
            trust_provider(root, "skill:graph-guru", True)
            after = resolve_capability(root, "repository.graph")
            self.assertEqual(after["selected"]["id"], "skill:graph-guru")
            self.assertTrue(after["trusted_selected"])

    def test_registered_plugin_manifest_is_detected_but_not_auto_invoked_without_adapter(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            reg = root / ".repo-context" / "providers.d"
            reg.mkdir(parents=True)
            (reg / "mcp.json").write_text(json.dumps({
                "schema": "repo-context-capabilities/v1",
                "provider": {"name": "codegraph-mcp", "type": "mcp"},
                "provides": ["repository.graph", "repository.symbols"]
            }), encoding="utf-8")
            detected = detect_providers(root, required=["repository.graph"], use_cache=False)
            self.assertTrue(any(p["id"] == "mcp:codegraph-mcp" for p in detected["providers"]))
            resolved = resolve_capability(root, "repository.graph")
            self.assertEqual(resolved["selected"]["source_type"], "native")
            self.assertTrue(any(p.get("id") == "mcp:codegraph-mcp" for p in resolved["potential_overlaps"]))

    def test_authorized_manifest_delegate_executes_without_shell_and_records_health(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            skill = root / ".agents" / "skills" / "graph-guru"
            skill.mkdir(parents=True)
            script = root / "provider.py"
            script.write_text('import json; print(json.dumps([{"path":"x.py","symbol":"run","content":"def run(): pass"}]))\n', encoding="utf-8")
            (skill / "SKILL.md").write_text("---\nname: graph-guru\ndescription: graph\n---\n", encoding="utf-8")
            (skill / "capabilities.json").write_text(json.dumps({
                "schema": "repo-context-capabilities/v1",
                "provides": [{"capability": "repository.graph", "command": {"argv": [sys.executable, str(script)]}}]
            }), encoding="utf-8")
            result = delegate_capability(root, "repository.graph", "debug x", allow_external_commands=True)
            self.assertTrue(result["delegated"])
            self.assertFalse(result["execution"]["shell"])
            self.assertEqual(result["blocks"][0]["symbol"], "run")
            health = ProviderHealth(root).summary("skill:graph-guru")["skill:graph-guru"]
            self.assertEqual(health["attempts"], 1)
            self.assertEqual(health["successes"], 1)

    def test_task_budget_blocks_when_limit_exhausted(self):
        with tempfile.TemporaryDirectory() as td:
            b = TaskBudget(pathlib.Path(td), "run", BudgetLimits(context_tokens=100, tool_calls=2))
            state = b.consume(context_tokens=100)
            self.assertFalse(state["allow_more_work"])
            self.assertIn("context_tokens", state["exceeded"])

    def test_lifecycle_demotes_hot_context(self):
        with tempfile.TemporaryDirectory() as td:
            life = ContextLifecycle(pathlib.Path(td), "s")
            life.touch("a", "x", 5000)
            life.touch("b", "y", 5000)
            result = life.evict(max_hot_tokens=5000)
            self.assertGreaterEqual(len(result["demoted_to_warm"]), 1)

    def test_tool_policy_flags_destructive_command(self):
        result = classify_command("git reset --hard HEAD~1")
        self.assertEqual(result["risk"], "destructive")

    def test_fanout_stops_at_high_coverage(self):
        result = recommend_fanout(0.92, unresolved_count=2, used_subagents=2, max_subagents=4)
        self.assertEqual(result["recommended_new_subagents"], 0)
        self.assertTrue(result["recommend_cancel_remaining"])

    def test_voi_penalizes_high_token_cost(self):
        small = value_of_information(relevance=1, uncertainty=1, novelty=1, graph_distance=0, estimated_tokens=100)
        large = value_of_information(relevance=1, uncertainty=1, novelty=1, graph_distance=0, estimated_tokens=10000)
        self.assertGreater(small["score"], large["score"])

    def test_trace_replay_is_observational(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            t = Trace(root, "r1")
            t.event("route", {"task": "debug"})
            replay = replay_summary(root, "r1")
            self.assertEqual(replay["counts"]["route"], 1)
            self.assertIn("does not re-execute", replay["note"])

    def test_attribution_is_labeled_heuristic(self):
        pack = {"files": [{"path": "a.py", "functions": ["run"], "classes": [], "types": [], "estimated_tokens": 100}], "symbols": []}
        result = analyze_context_usage(pack, "run is the relevant function")
        self.assertEqual(result["classification"], "heuristic-lexical-attribution")
        self.assertEqual(result["lexically_attributed_tokens"], 100)

    def test_benchmark_can_measure_expected_path_recall(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "payment.py").write_text("def charge(amount):\n    return amount\n", encoding="utf-8")
            result = benchmark_tasks(root, [{"task": "payment charge", "expected_paths": ["payment.py"]}], budget=1200)
            self.assertEqual(result["tasks"][0]["expected_path_recall"], 1.0)
            self.assertFalse(result["tasks"][0]["correctness_claim"])


if __name__ == "__main__":
    unittest.main()
