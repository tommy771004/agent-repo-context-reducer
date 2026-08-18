from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import time
import unittest

from repo_context import __version__
from repo_context.answer_evaluation import evaluate_final_answer
from repo_context.capabilities import NATIVE_CAPABILITIES
from repo_context.cli import main
from repo_context.runtime_adapters import (
    CallableRuntimeAdapter,
    CancellationToken,
    build_runtime_invocation,
    register_runtime_adapter,
    runtime_adapter_status,
    unregister_runtime_adapter,
)
from repo_context.runtime_engine import execute_runtime, load_runtime_config
from repo_context.schema_registry import list_schemas, validate_contract
from repo_context.telemetry import normalize_usage
from repo_context.runtime_context import slice_context_pack


class VersionAndRuntimeContractTests(unittest.TestCase):
    def test_version_is_v20(self):
        self.assertGreaterEqual(tuple(map(int, __version__.split("."))), (2, 0, 0))

    def test_v20_schemas_are_registered(self):
        names = {item["name"] for item in list_schemas()}
        self.assertTrue({
            "runtime-invocation",
            "runtime-result",
            "runtime-telemetry",
            "runtime-config",
            "final-answer-evaluation",
        } <= names)

    def test_v20_capabilities_are_declared(self):
        expected = {
            "runtime.adapter",
            "runtime.execute",
            "runtime.cancellation",
            "runtime.backpressure",
            "runtime.telemetry",
            "quality.final-answer-evaluation",
        }
        self.assertTrue(expected <= NATIVE_CAPABILITIES)

    def test_runtime_invocation_never_grants_context_instruction_authority(self):
        request = build_runtime_invocation(
            node={"id": "w", "role": "worker"},
            task="debug payment",
            task_type="debug",
            model_tier="standard",
            dependency_handoffs={},
            context_pack={"files": []},
            lane_budget={},
            run_id="r",
        )
        self.assertFalse(request["policy"]["instruction_authority_from_context"])
        self.assertTrue(validate_contract("runtime-invocation", request)["valid"])


class FinalAnswerEvaluationTests(unittest.TestCase):
    def test_required_and_forbidden_claims(self):
        case = {"required_claims": ["payment async"], "forbidden_claims": ["payment always sync"]}
        passed = evaluate_final_answer("Payment async via queue", case)
        self.assertTrue(passed["passed"])
        failed = evaluate_final_answer("Payment async but payment always sync", case)
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["forbidden_hits"], ["payment always sync"])

    def test_structured_required_fields_and_decision(self):
        result = evaluate_final_answer(
            {"answer": "done", "decision": "pass", "evidence": ["x"]},
            {"required_fields": ["evidence"], "expected_decision": "pass"},
        )
        self.assertTrue(result["passed"])
        self.assertTrue(validate_contract("final-answer-evaluation", result)["valid"])


class RuntimeAdapterTests(unittest.TestCase):
    def test_runtime_config_contract_is_enforced_for_dict_input(self):
        with self.assertRaisesRegex(ValueError, "invalid runtime config"):
            load_runtime_config({})
        self.assertEqual(load_runtime_config({"adapter": "subprocess"})["adapter"], "subprocess")

    def test_runtime_status_includes_native_subprocess(self):
        status = {x["name"]: x for x in runtime_adapter_status()}
        self.assertIn("subprocess", status)
        self.assertTrue(status["subprocess"]["requires_explicit_authorization"])

    def test_callable_adapter_normalizes_host_exception(self):
        adapter = CallableRuntimeAdapter("boom", lambda request, cancellation: (_ for _ in ()).throw(RuntimeError("boom")))
        result = adapter.invoke({"role": "worker"}, root=pathlib.Path.cwd(), cancellation=CancellationToken())
        self.assertEqual(result["status"], "failed")
        self.assertIn("RuntimeError", result["error"])

    def test_subprocess_runtime_is_blocked_without_explicit_authorization(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            script = root / "worker.py"
            script.write_text("import json,sys; json.load(sys.stdin); json.dump({'summary':'ok','usage':{'input_tokens':1,'output_tokens':1}},sys.stdout)\n", encoding="utf-8")
            config = {"adapter": "subprocess", "default": {"argv": [sys.executable, str(script)]}, "enforce_quality_gate": False}
            result = execute_runtime("Explain this function", root, runtime_config=config, context_tokens=1000, output_tokens=1000, model_calls=4, authorize_external=False)
            self.assertFalse(result["success"])
            self.assertTrue(any(x.get("status") == "blocked" for x in result["nodes"].values()))

    def test_subprocess_stdout_limit_is_enforced_while_running(self):
        from repo_context.runtime_adapters import SubprocessRuntimeAdapter
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            script = root / "worker.py"
            script.write_text("import sys; sys.stdout.write('x' * 6000000); sys.stdout.flush()\n", encoding="utf-8")
            adapter = SubprocessRuntimeAdapter({"default": {"argv": [sys.executable, str(script)], "timeout_seconds": 5}}, authorized=True)
            result = adapter.invoke({"task": "x", "role": "worker", "node_id": "w"}, root=root, cancellation=CancellationToken())
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["reason"], "runtime-output-too-large")
            self.assertLessEqual(result["stdout_bytes_retained"], result["stdout_limit_bytes"])

    def test_subprocess_runtime_executes_with_shell_false_when_authorized(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            script = root / "worker.py"
            script.write_text(
                "import json,sys\n"
                "r=json.load(sys.stdin)\n"
                "role=r.get('role')\n"
                "o={'decision':'pass','score':0.99,'failures':[],'evidence':['ok']} if role=='grader' else {'summary':'worker ok'}\n"
                "o['usage']={'input_tokens':2,'output_tokens':2,'cost_usd':0.001,'provider':'mock'}\n"
                "json.dump(o,sys.stdout)\n",
                encoding="utf-8",
            )
            config = {"adapter": "subprocess", "default": {"argv": [sys.executable, str(script)], "timeout_seconds": 5}}
            result = execute_runtime("Explain this function", root, runtime_config=config, context_tokens=1000, output_tokens=1000, model_calls=4, authorize_external=True)
            self.assertTrue(result["success"])
            self.assertEqual(result["nodes"]["work"]["execution"]["shell"], False)
            self.assertEqual(result["telemetry"]["cost_completeness"], "complete")
            self.assertGreater(result["telemetry"]["reported_cost_usd"], 0)


class RuntimeEngineTests(unittest.TestCase):
    def tearDown(self):
        for name in ("unit-runtime", "retry-runtime", "cancel-runtime", "reject-runtime"):
            unregister_runtime_adapter(name)

    @staticmethod
    def _success_fn(request, cancellation):
        role = request["role"]
        if role == "researcher":
            time.sleep(0.04)
        usage = {"input_tokens": 5, "output_tokens": 5, "cost_usd": 0.0001, "provider": "unit", "model": request["model_tier"]}
        if role == "grader":
            return {"decision": "pass", "score": 0.99, "failures": [], "evidence": ["verified"], "usage": usage}
        if role == "integrator":
            return {"answer": "Payment status updates are asynchronous", "usage": usage}
        return {
            "summary": f"{role} done",
            "findings": [{"claim": "Payment status updates are asynchronous", "evidence": role, "source": f"runtime:{request['node_id']}", "canonicalKey": "payment|mode", "value": "async"}],
            "usage": usage,
        }

    def test_lane_context_slicing_respects_pre_ranked_evidence_budget(self):
        pack = {
            "task": "x",
            "strategy": "test",
            "repository_provenance": {},
            "trust_summary": {},
            "coverage": {},
            "notes": [],
            "external_context": [],
            "symbols": [{"path": "a.py", "name": "a", "content": "x" * 200}],
            "files": [{"path": "b.py", "functions": ["b"]}],
        }
        sliced = slice_context_pack(pack, 200)
        self.assertIsNotNone(sliced)
        self.assertLessEqual(sliced["budget"]["estimated_used_tokens"], 200)
        self.assertFalse(sliced["budget"]["overflow"])

    def test_grader_and_integrator_receive_fan_in_synthesis_packet(self):
        seen = {}
        def fn(request, cancellation):
            seen[request["role"]] = {
                "synthesis_packet": request.get("synthesis_packet"),
                "dependency_handoffs": request.get("dependency_handoffs"),
                "dependency_context_mode": request.get("dependency_context_mode"),
            }
            return self._success_fn(request, cancellation)
        register_runtime_adapter("unit-runtime", lambda config: CallableRuntimeAdapter("unit-runtime", fn))
        with tempfile.TemporaryDirectory() as td:
            result = execute_runtime(
                "Autonomously implement an end-to-end payment migration across the entire project and ship production-ready integration",
                td, runtime_config={"adapter": "unit-runtime", "max_attempts": 1}, adapter_name="unit-runtime",
                context_tokens=5000, output_tokens=5000, model_calls=12, concurrency=2,
            )
        self.assertTrue(result["success"])
        self.assertIsInstance(seen.get("grader"), dict)
        self.assertTrue(seen["grader"]["synthesis_packet"]["findings"])
        self.assertTrue(seen["grader"]["synthesis_packet"]["filter_audit"]["passed"])
        self.assertEqual(seen["grader"]["dependency_context_mode"], "status-only+synthesis-packet")
        self.assertTrue(all("handoff" not in item for item in seen["grader"]["dependency_handoffs"].values()))
        self.assertIsInstance(seen.get("integrator"), dict)
        self.assertTrue(seen["integrator"]["synthesis_packet"]["findings"])
        self.assertEqual(seen["integrator"]["dependency_context_mode"], "status-only+synthesis-packet")

    def test_autonomous_runtime_executes_parallel_waves_and_final_gate(self):
        register_runtime_adapter("unit-runtime", lambda config: CallableRuntimeAdapter("unit-runtime", self._success_fn))
        with tempfile.TemporaryDirectory() as td:
            result = execute_runtime(
                "Autonomously implement an end-to-end payment migration across the entire project and ship production-ready integration",
                td,
                runtime_config={"adapter": "unit-runtime", "max_attempts": 1},
                adapter_name="unit-runtime",
                context_tokens=5000,
                output_tokens=5000,
                model_calls=12,
                concurrency=2,
                final_answer_case={"required_claims": ["Payment status updates are asynchronous"]},
            )
        self.assertTrue(result["success"])
        self.assertGreaterEqual(result["backpressure"]["peak_active_workers"], 2)
        self.assertEqual(result["nodes"]["grade"]["quality_gate"]["decision"], "pass")
        self.assertTrue(result["final_answer_evaluation"]["passed"])
        self.assertTrue(validate_contract("runtime-result", result)["valid"])
        self.assertTrue(validate_contract("runtime-telemetry", result["telemetry"])["valid"])

    def test_retry_escalates_tier_after_high_risk_failure(self):
        seen: list[tuple[str, int, str]] = []
        attempts: dict[str, int] = {}

        def fn(request, cancellation):
            node = request["node_id"]
            attempts[node] = attempts.get(node, 0) + 1
            seen.append((node, request["attempt"], request["model_tier"]))
            if request["role"] != "grader" and attempts[node] == 1:
                return {"status": "failed", "reason": "transient", "payload": None}
            if request["role"] == "grader":
                return {"decision": "pass", "score": 0.99, "failures": [], "evidence": ["ok"], "usage": {"input_tokens": 1, "output_tokens": 1}}
            return {"summary": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}}

        register_runtime_adapter("retry-runtime", lambda config: CallableRuntimeAdapter("retry-runtime", fn))
        with tempfile.TemporaryDirectory() as td:
            result = execute_runtime(
                "Fix production payment authentication failure",
                td,
                runtime_config={"adapter": "retry-runtime"},
                adapter_name="retry-runtime",
                context_tokens=5000,
                output_tokens=5000,
                model_calls=10,
            )
        self.assertTrue(result["success"])
        worker_attempts = [x for x in seen if x[0] == "work"]
        self.assertGreaterEqual(len(worker_attempts), 2)
        self.assertEqual(worker_attempts[0][2], "standard")
        self.assertEqual(worker_attempts[1][2], "strong")

    def test_quality_gate_reject_cancels_finalize(self):
        def fn(request, cancellation):
            if request["role"] == "grader":
                return {"decision": "reject", "score": 0.2, "failures": ["bad"], "evidence": []}
            return {"summary": "ok", "findings": [{"claim": "x", "evidence": "x", "source": "x"}], "usage": {"input_tokens": 1, "output_tokens": 1}}

        register_runtime_adapter("reject-runtime", lambda config: CallableRuntimeAdapter("reject-runtime", fn))
        with tempfile.TemporaryDirectory() as td:
            result = execute_runtime(
                "Autonomously implement an end-to-end migration across the entire project and ship production-ready integration",
                td,
                runtime_config={"adapter": "reject-runtime", "max_attempts": 1},
                adapter_name="reject-runtime",
                context_tokens=5000,
                output_tokens=5000,
                model_calls=12,
            )
        self.assertFalse(result["success"])
        self.assertEqual(result["nodes"]["grade"]["status"], "quality-gate-failed")
        self.assertEqual(result["nodes"]["finalize"]["status"], "cancelled")

    def test_fail_fast_cancels_parallel_worker(self):
        def fn(request, cancellation):
            if request["node_id"] == "research-a":
                return {"status": "failed", "reason": "boom", "payload": None}
            if request["node_id"] == "research-b":
                for _ in range(100):
                    if cancellation.cancelled:
                        return {"status": "cancelled", "reason": "observed-token", "payload": None}
                    time.sleep(0.005)
            if request["role"] == "grader":
                return {"decision": "pass", "score": 0.99, "failures": [], "evidence": []}
            return {"summary": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}}

        register_runtime_adapter("cancel-runtime", lambda config: CallableRuntimeAdapter("cancel-runtime", fn))
        with tempfile.TemporaryDirectory() as td:
            result = execute_runtime(
                "Autonomously implement an end-to-end migration across the entire project and ship production-ready integration",
                td,
                runtime_config={"adapter": "cancel-runtime", "max_attempts": 1},
                adapter_name="cancel-runtime",
                context_tokens=5000,
                output_tokens=5000,
                model_calls=12,
                concurrency=2,
                fail_fast=True,
            )
        self.assertFalse(result["success"])
        self.assertTrue(result["cancelled"])
        self.assertIn(result["nodes"]["research-b"]["status"], {"cancelled", "success"})
        self.assertIn(result["nodes"]["implement"]["status"], {"cancelled", "skipped"})

    def test_exact_token_limit_can_complete_without_false_failure(self):
        def fn(request, cancellation):
            usage = {"input_tokens": 1, "output_tokens": 1}
            if request["role"] == "grader":
                return {"decision": "pass", "score": 0.99, "failures": [], "evidence": ["ok"], "usage": usage}
            return {"summary": "ok", "usage": usage}
        register_runtime_adapter("unit-runtime", lambda config: CallableRuntimeAdapter("unit-runtime", fn))
        with tempfile.TemporaryDirectory() as td:
            result = execute_runtime(
                "Explain this function", td, runtime_config={"adapter": "unit-runtime", "max_attempts": 1},
                adapter_name="unit-runtime", context_tokens=2, output_tokens=2, model_calls=2,
            )
        self.assertTrue(result["success"])
        self.assertEqual(result["backpressure"]["input_tokens_used"], 2)
        self.assertEqual(result["backpressure"]["output_tokens_used"], 2)
        self.assertEqual(result["backpressure"]["budget_overshoot"], [])

    def test_runtime_wall_deadline_cancels_authorized_subprocess(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            script = root / "sleep_worker.py"
            script.write_text("import json,sys,time; json.load(sys.stdin); time.sleep(5); json.dump({'summary':'late'},sys.stdout)\n", encoding="utf-8")
            config = {"adapter": "subprocess", "wall_seconds": 1, "cancellation_grace_seconds": 1, "default": {"argv": [sys.executable, str(script)], "timeout_seconds": 10}, "enforce_quality_gate": False}
            started = time.perf_counter()
            result = execute_runtime("Explain this function", root, runtime_config=config, context_tokens=1000, output_tokens=1000, model_calls=4, authorize_external=True)
            elapsed = time.perf_counter() - started
        self.assertFalse(result["success"])
        self.assertTrue(result["cancelled"])
        self.assertIn("wall_seconds", result["backpressure"]["budget_exhausted"])
        self.assertLess(elapsed, 4.0)

    def test_model_call_budget_applies_real_backpressure(self):
        register_runtime_adapter("unit-runtime", lambda config: CallableRuntimeAdapter("unit-runtime", self._success_fn))
        with tempfile.TemporaryDirectory() as td:
            result = execute_runtime(
                "Autonomously implement an end-to-end migration across the entire project and ship production-ready integration",
                td,
                runtime_config={"adapter": "unit-runtime", "max_attempts": 1},
                adapter_name="unit-runtime",
                context_tokens=5000,
                output_tokens=5000,
                model_calls=2,
                concurrency=2,
            )
        self.assertFalse(result["success"])
        self.assertIn("model_calls", result["backpressure"]["budget_exhausted"])
        self.assertLessEqual(result["backpressure"]["model_calls_used"], 2)


class TelemetryTests(unittest.TestCase):
    def test_cost_is_not_inferred_when_provider_does_not_report_it(self):
        usage = normalize_usage(
            {"status": "success", "payload": {"summary": "x"}, "latency_ms": 1},
            request={"task": "x"},
        )
        self.assertIsNone(usage["cost_usd"])
        self.assertEqual(usage["cost_source"], "unreported")


class RuntimeCliTests(unittest.TestCase):
    def test_runtime_execute_cli_returns_nonzero_when_external_execution_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            script = root / "worker.py"
            script.write_text("import json,sys; json.load(sys.stdin); json.dump({'summary':'ok'},sys.stdout)\n", encoding="utf-8")
            config = root / "runtime.json"
            config.write_text(json.dumps({"adapter":"subprocess","enforce_quality_gate":False,"default":{"argv":[sys.executable,str(script)]}}), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["runtime","execute","Explain this function","--repo",td,"--config",str(config),"--no-context"])
            self.assertEqual(rc, 3)
            self.assertFalse(json.loads(out.getvalue())["success"])

    def test_runtime_status_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(["runtime", "status"])
        self.assertEqual(rc, 0)
        data = json.loads(out.getvalue())
        self.assertTrue(any(x["name"] == "subprocess" for x in data["adapters"]))

    def test_evaluate_final_cli_returns_nonzero_on_failed_gate(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(["evaluate-final", "wrong", '{"required_claims":["payment async"]}'])
        self.assertEqual(rc, 3)
        self.assertFalse(json.loads(out.getvalue())["passed"])

    def test_evaluate_final_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(["evaluate-final", "payment async", '{"required_claims":["payment async"]}'])
        self.assertEqual(rc, 0)
        self.assertTrue(json.loads(out.getvalue())["passed"])


if __name__ == "__main__":
    unittest.main()
