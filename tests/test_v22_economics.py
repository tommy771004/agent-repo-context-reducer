from __future__ import annotations

import unittest
import tempfile

from repo_context.adaptive_reduction import choose_reduction_mode, project_reduction_mode
from repo_context.cli import main as cli_main
from repo_context.fan_in import reduce_worker_outputs
from repo_context.filter_audit import audit_filter_reduction
from repo_context.model_packet import split_model_packet
from repo_context.model_context import split_model_context, project_verification_context
from repo_context.schema_registry import list_schemas, validate_contract
from repo_context.scenario_simulation import simulate_scenarios
from repo_context.synthesis_packet import build_synthesis_packet
from repo_context.telemetry import normalize_usage
from repo_context.runtime_adapters import CallableRuntimeAdapter, register_runtime_adapter, unregister_runtime_adapter
from repo_context.runtime_engine import execute_runtime
from repo_context.token_economics import summarize_token_economics


class V22ThinModelPacketTests(unittest.TestCase):
    def _packet(self):
        reduction = reduce_worker_outputs([
            {"worker": "a", "findings": [{"claim": "payment async", "evidence": "queue.publish", "source": "payment.py", "canonicalKey": "payment|mode", "value": "async"}]},
            {"worker": "b", "findings": [{"claim": "payment async", "evidence": "consumer", "source": "payment.py", "canonicalKey": "payment|mode", "value": "async"}]},
        ])
        packet = build_synthesis_packet(reduction, max_estimated_tokens=5000)
        packet["filter_audit"] = audit_filter_reduction(reduction)
        return packet

    def test_model_packet_strips_control_plane_but_keeps_evidence(self):
        split = split_model_packet(self._packet())
        model = split["model_payload"]
        sidecar = split["sidecar"]
        self.assertTrue(model["findings"])
        self.assertEqual(model["policy"]["content_authority"], "evidence-only")
        self.assertNotIn("reducer_summary", model)
        self.assertNotIn("trust_summary", model)
        self.assertNotIn("budget", model)
        self.assertIn("reducer_summary", sidecar)
        self.assertTrue(model["filter_audit"]["passed"])
        self.assertLess(split["metrics"]["model_payload_tokens"], split["metrics"]["rich_packet_tokens"])
        self.assertTrue(validate_contract("model-packet", model)["valid"])

    def test_source_references_deduplicate_repeated_source(self):
        split = split_model_packet(self._packet())
        model = split["model_payload"]
        self.assertEqual(len(model["sources"]), 1)
        self.assertEqual(model["findings"][0]["source_ref"], "S1")


class V22ThinModelContextTests(unittest.TestCase):
    def test_context_projection_removes_control_metadata(self):
        rich = {
            "task": "x", "repository_provenance": {"commit": "abc"}, "trust_summary": {"blocks": 2},
            "coverage": {"lexical": 1.0}, "budget": {"estimated_used_tokens": 500},
            "notes": ["control"],
            "files": [{"path": "a.py", "imports": ["b"], "provenance": {"blob": "1"}, "trust": {"instruction_authority": False}, "voi": {"score": .8}}],
            "symbols": [{"path": "a.py", "name": "f", "content": "return 1", "provenance": {"blob": "1"}, "trust": {"instruction_authority": False}}],
            "external_context": [],
        }
        split = split_model_context(rich)
        model = split["model_payload"]
        self.assertNotIn("repository_provenance", model)
        self.assertNotIn("trust_summary", model)
        self.assertNotIn("provenance", model["symbols"][0])
        self.assertNotIn("trust", model["files"][0])
        self.assertIn("provenance", split["sidecar"]["symbol_metadata"][0])
        self.assertLess(split["metrics"]["model_context_tokens"], split["metrics"]["rich_context_tokens"] )
        self.assertTrue(validate_contract("model-context", model)["valid"])


class V22TokenEconomicsTests(unittest.TestCase):
    def test_token_amplification_can_report_regression(self):
        result = summarize_token_economics(
            aggregate_input_tokens=11000,
            aggregate_output_tokens=1500,
            baseline_input_tokens=9000,
            baseline_output_tokens=1000,
        )
        self.assertFalse(result["token_efficient"])
        self.assertGreater(result["token_amplification_ratio"], 1.0)
        self.assertLess(result["net_token_savings"], 0)
        self.assertTrue(validate_contract("token-economics", result)["valid"])

    def test_usage_splits_data_and_control_plane_without_exceeding_total_estimate(self):
        request = {
            "task": "fix x",
            "role": "grader",
            "context": {"files": [{"path": "a.py", "content": "x" * 200}]},
            "synthesis_packet": {"findings": [{"claim": "x", "evidence": "e"}]},
            "policy": {"a": "b"},
        }
        usage = normalize_usage({"status": "success", "payload": {"ok": True}}, request=request)
        b = usage["request_token_breakdown"]
        self.assertEqual(b["data_plane_tokens_estimated"] + b["control_plane_tokens_estimated"], b["total_input_tokens_estimated"])

    def test_status_only_handoffs_count_as_control_plane(self):
        request = {"task": "grade", "dependency_handoffs": {"work": {"status": "success", "role": "worker", "handoff_available": True}}}
        usage = normalize_usage({"status": "success", "payload": {}}, request=request)
        b = usage["request_token_breakdown"]
        self.assertEqual(b["data_plane_tokens_estimated"], 0)
        self.assertGreater(b["control_plane_tokens_estimated"], 0)

    def test_mixed_provider_and_estimated_counts_are_labeled_directional(self):
        result = summarize_token_economics(
            aggregate_input_tokens=900, aggregate_output_tokens=100,
            baseline_input_tokens=1200, baseline_output_tokens=100,
            baseline_tokens_source="estimated",
            pipeline_input_tokens_source="provider-reported",
            pipeline_output_tokens_source="provider-reported",
        )
        self.assertEqual(result["measurement"]["comparison_quality"], "mixed-measurement")
        self.assertFalse(result["measurement"]["savings_claim_comparable"])

    def test_estimator_only_counts_are_comparable_but_not_billing_claim(self):
        result = summarize_token_economics(
            aggregate_input_tokens=900, aggregate_output_tokens=100,
            baseline_input_tokens=1200, baseline_output_tokens=100,
        )
        self.assertEqual(result["measurement"]["comparison_quality"], "comparable-estimates")
        self.assertTrue(result["measurement"]["savings_claim_comparable"])
        self.assertIn("not a provider billing", result["measurement"]["interpretation"])

    def test_verification_context_is_source_targeted(self):
        rich = {
            "files": [{"path": "a.py", "content": "A"}, {"path": "b.py", "content": "B"}],
            "symbols": [{"path": "a.py", "name": "fa", "content": "return 1"}, {"path": "b.py", "name": "fb", "content": "return 2"}],
            "external_context": [],
        }
        packet = {"sources": {"S1": "b.py"}}
        projected = project_verification_context(rich, packet, max_tokens=2000)
        model = projected["model_payload"]
        self.assertEqual({x["path"] for x in model["files"]}, {"b.py"})
        self.assertEqual({x["path"] for x in model["symbols"]}, {"b.py"})
        self.assertEqual(model["policy"]["projection"], "source-targeted-verification")


class V22AdaptiveScenarioTests(unittest.TestCase):
    def test_small_low_dup_task_routes_direct(self):
        route = choose_reduction_mode("fix typo", source_tokens=2500, duplicate_ratio=0.02, conflict_ratio=0.0)
        self.assertEqual(route["selected_mode"], "direct")
        self.assertTrue(validate_contract("adaptive-reduction", route)["valid"])

    def test_light_projection_counts_worker_and_grader(self):
        projection = project_reduction_mode("light", source_tokens=12000, duplicate_ratio=0.4)
        self.assertEqual(projection["model_calls"], 2)

    def test_low_risk_medium_no_dup_does_not_add_grader_for_nominal_savings(self):
        route = choose_reduction_mode(
            "inspect helper behavior", source_tokens=12000, duplicate_ratio=0.0, conflict_ratio=0.0,
            complexity={"level": "focused"}, risk={"level": "low"},
        )
        self.assertEqual(route["selected_mode"], "direct")

    def test_medium_risk_requires_at_least_light(self):
        route = choose_reduction_mode(
            "review a bounded change", source_tokens=5000, duplicate_ratio=0.0, conflict_ratio=0.0,
            complexity={"level": "focused"}, risk={"level": "medium"},
        )
        self.assertEqual(route["selected_mode"], "light")
        self.assertFalse(route["eligibility"]["direct"]["eligible"])

    def test_local_dedup_benefit_is_shared_by_direct_and_light(self):
        direct = project_reduction_mode("direct", source_tokens=10000, duplicate_ratio=0.5)
        light = project_reduction_mode("light", source_tokens=10000, duplicate_ratio=0.5)
        self.assertEqual(direct["filtered_context_tokens"], light["filtered_context_tokens"])

    def test_small_high_risk_task_still_routes_full(self):
        route = choose_reduction_mode("security production credential deployment", source_tokens=3000, duplicate_ratio=0.0, conflict_ratio=0.0)
        self.assertEqual(route["selected_mode"], "full")
        self.assertFalse(route["eligibility"]["direct"]["eligible"] )
        self.assertFalse(route["eligibility"]["light"]["eligible"] )

    def test_explicit_conflict_language_requires_parallel_evidence(self):
        route = choose_reduction_mode("compare conflicting evidence about payment behavior", source_tokens=4000, duplicate_ratio=0.0, conflict_ratio=0.0)
        self.assertEqual(route["selected_mode"], "full")
        self.assertTrue(route["inputs"]["requires_parallel_evidence"] )

    def test_high_conflict_complex_task_cannot_route_direct_or_light(self):
        route = choose_reduction_mode(
            "review architecture conflict across repository",
            source_tokens=30000,
            duplicate_ratio=0.2,
            conflict_ratio=0.15,
            requires_parallel_evidence=True,
        )
        self.assertEqual(route["selected_mode"], "full")
        self.assertFalse(route["eligibility"]["direct"]["eligible"])
        self.assertFalse(route["eligibility"]["light"]["eligible"])

    def test_default_scenarios_cover_all_three_modes_and_prevent_always_full(self):
        simulation = simulate_scenarios()
        selected = {row["selected_mode"] for row in simulation["scenarios"]}
        self.assertEqual(selected, {"direct", "light", "full"})
        self.assertEqual(simulation["recommended_policy"], "adaptive")
        self.assertGreater(simulation["aggregate"]["adaptive_savings_vs_always_full"], 0)
        self.assertTrue(validate_contract("reduction-simulation", simulation)["valid"])

    def test_full_can_be_token_regression_but_remains_required_for_conflict(self):
        simulation = simulate_scenarios()
        row = next(x for x in simulation["scenarios"] if x["name"] == "conflicting-evidence")
        self.assertGreater(row["strategies"]["full"]["total_model_tokens"], row["strategies"]["direct"]["total_model_tokens"])
        self.assertEqual(row["selected_mode"], "full")
        self.assertFalse(row["eligibility"]["direct"]["eligible"])

    def test_runtime_config_rejects_unknown_reduction_mode(self):
        self.assertFalse(validate_contract("runtime-config", {"adapter": "x", "reduction_mode": "magic"})["valid"] )

    def test_new_contracts_are_exposed(self):
        names = {x["name"] for x in list_schemas()}
        self.assertTrue({"model-packet", "model-context", "token-economics", "adaptive-reduction", "reduction-simulation"}.issubset(names))


class V22AdaptiveRuntimeTests(unittest.TestCase):
    def tearDown(self):
        unregister_runtime_adapter("econ-runtime")

    @staticmethod
    def _fn(request, cancellation):
        if request["role"] == "grader":
            return {"decision": "pass", "score": 0.99, "failures": [], "evidence": ["ok"]}
        return {"summary": "ok", "findings": [{"claim": "ok", "evidence": "e", "source": "a.py"}]}

    def test_auto_mode_reduces_small_task_to_one_model_call(self):
        register_runtime_adapter("econ-runtime", lambda config: CallableRuntimeAdapter("econ-runtime", self._fn))
        with tempfile.TemporaryDirectory() as td:
            result = execute_runtime(
                "fix typo", td, runtime_config={"adapter": "econ-runtime", "max_attempts": 1},
                adapter_name="econ-runtime", context_pack={"files": [], "symbols": [], "external_context": []},
                context_tokens=3000, output_tokens=1000, model_calls=4, reduction_mode="auto",
            )
        self.assertTrue(result["success"])
        self.assertEqual(result["plan"]["adaptive_reduction"]["effective_mode"], "direct")
        self.assertEqual(result["backpressure"]["model_calls_used"], 1)
        self.assertEqual(set(result["nodes"]), {"work"})

    def test_auto_small_task_uses_fewer_actual_runtime_tokens_than_compat(self):
        register_runtime_adapter("econ-runtime", lambda config: CallableRuntimeAdapter("econ-runtime", self._fn))
        context = {
            "files": [{"path": "a.py", "imports": []}],
            "symbols": [{"path": "a.py", "name": "f", "content": "return 1" * 40}],
            "external_context": [],
        }
        with tempfile.TemporaryDirectory() as td:
            compat = execute_runtime(
                "fix typo", td, runtime_config={"adapter": "econ-runtime", "max_attempts": 1}, adapter_name="econ-runtime",
                context_pack=context, context_tokens=5000, output_tokens=2000, model_calls=4, reduction_mode="compat", checkpoint=False,
            )
            auto = execute_runtime(
                "fix typo", td, runtime_config={"adapter": "econ-runtime", "max_attempts": 1}, adapter_name="econ-runtime",
                context_pack=context, context_tokens=5000, output_tokens=2000, model_calls=4, reduction_mode="auto", checkpoint=False,
            )
        self.assertLess(auto["telemetry"]["total_tokens"], compat["telemetry"]["total_tokens"] )
        self.assertLess(auto["backpressure"]["model_calls_used"], compat["backpressure"]["model_calls_used"] )

    def test_auto_explicit_conflict_creates_two_parallel_evidence_lanes(self):
        register_runtime_adapter("econ-runtime", lambda config: CallableRuntimeAdapter("econ-runtime", self._fn))
        with tempfile.TemporaryDirectory() as td:
            result = execute_runtime(
                "compare conflicting evidence about feature behavior", td,
                runtime_config={"adapter": "econ-runtime", "max_attempts": 1}, adapter_name="econ-runtime",
                context_tokens=6000, output_tokens=3000, model_calls=6, reduction_mode="auto",
            )
        self.assertTrue(result["success"])
        self.assertEqual(result["plan"]["adaptive_reduction"]["effective_mode"], "full")
        self.assertEqual(result["plan"]["schedule"]["max_parallel_width"], 2)
        self.assertTrue(result["plan"]["schedule"].get("parallel_evidence_required"))
        self.assertTrue({"research-a", "research-b", "grade", "finalize"}.issubset(result["nodes"]))

    def test_ineligible_forced_direct_mode_is_rejected(self):
        register_runtime_adapter("econ-runtime", lambda config: CallableRuntimeAdapter("econ-runtime", self._fn))
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                execute_runtime(
                    "Autonomously migrate the entire project architecture end-to-end", td,
                    runtime_config={"adapter": "econ-runtime"}, adapter_name="econ-runtime",
                    context_tokens=30000, output_tokens=4000, model_calls=12, reduction_mode="direct",
                )

    def test_runtime_model_request_does_not_serialize_context_sidecar(self):
        seen = []
        def capture(request, cancellation):
            seen.append(request)
            return self._fn(request, cancellation)
        register_runtime_adapter("econ-runtime", lambda config: CallableRuntimeAdapter("econ-runtime", capture))
        context = {
            "files": [{"path": "a.py", "imports": [], "provenance": {"blob": "secret-control"}, "trust": {"instruction_authority": False}}],
            "symbols": [{"path": "a.py", "name": "f", "content": "return 1", "provenance": {"blob": "secret-control"}}],
            "external_context": [], "repository_provenance": {"commit": "abc"}, "trust_summary": {"blocks": 1},
        }
        with tempfile.TemporaryDirectory() as td:
            result = execute_runtime(
                "fix function", td, runtime_config={"adapter": "econ-runtime", "max_attempts": 1},
                adapter_name="econ-runtime", context_pack=context, context_tokens=5000, output_tokens=2000,
                model_calls=4, reduction_mode="light",
            )
        self.assertTrue(result["success"])
        self.assertEqual(len(seen), 2)
        model_contexts = [req.get("context") for req in seen if isinstance(req.get("context"), dict)]
        self.assertTrue(model_contexts)
        for ctx in model_contexts:
            self.assertNotIn("repository_provenance", ctx)
            self.assertNotIn("trust_summary", ctx)
            if ctx.get("symbols"):
                self.assertNotIn("provenance", ctx["symbols"][0])
        grader = next(req for req in seen if req["role"] == "grader")
        self.assertNotIn("reducer_summary", grader["synthesis_packet"] )
        self.assertNotIn("trust_summary", grader["synthesis_packet"] )
        self.assertGreater(result["telemetry"]["control_plane_input_tokens_estimated"], 0)


class V22EconomicsCliTests(unittest.TestCase):
    def test_simulate_reduction_cli_is_wired(self):
        self.assertEqual(cli_main(["simulate-reduction"]), 0)

    def test_reduction_route_cli_is_wired(self):
        self.assertEqual(cli_main(["reduction-route", "fix typo", "--source-tokens", "3000"]), 0)

    def test_model_packet_cli_is_wired(self):
        reduction = reduce_worker_outputs([{
            "worker": "a", "findings": [{"claim": "x", "evidence": "e", "source": "a.py"}]
        }])
        packet = build_synthesis_packet(reduction, max_estimated_tokens=3000)
        import json, pathlib
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "packet.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            self.assertEqual(cli_main(["model-packet", str(path)]), 0)


if __name__ == "__main__":
    unittest.main()
