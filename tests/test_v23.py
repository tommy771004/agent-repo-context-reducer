from __future__ import annotations

import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from repo_context import __version__
from repo_context.capabilities import CORE_CAPABILITIES, ADVISORY_CAPABILITIES, NATIVE_CAPABILITIES
from repo_context.cli import main
from repo_context.context_evidence import make_context_evidence, verify_context_evidence
from repo_context.context_planner import build_context
from repo_context.context_store import RepositoryContextStore, build_repository_context_store, invalidate_stale_context
from repo_context.context_safety import assess_context_sufficiency
from repo_context.model_context import split_model_context
from repo_context.maintenance import state_inventory
from repo_context.recall import recall_repository_context
from repo_context.recall_benchmark import benchmark_context_recall
from repo_context.scanner import build_index
from repo_context.schema_registry import list_schemas, validate_contract


def make_repo(root: pathlib.Path) -> None:
    (root / "app.py").write_text(
        "from payment import charge\n\ndef checkout():\n    return charge()\n",
        encoding="utf-8",
    )
    (root / "payment.py").write_text(
        "def charge():\n    return retry_payment()\n\ndef retry_payment():\n    return 'queued'\n",
        encoding="utf-8",
    )
    (root / "audit.py").write_text(
        "def record_payment_event(event):\n    return event\n",
        encoding="utf-8",
    )
    (root / "unrelated.py").write_text("def unrelated():\n    return 1\n", encoding="utf-8")


class V23EvidenceContractTests(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in __version__.split(".")), (2, 3, 0))

    def test_evidence_contract_is_repository_scoped(self):
        item = make_context_evidence(kind="symbol", path="payment.py", symbol="retry_payment", start_line=4, end_line=5, revision="r1")
        self.assertEqual(item["classification"], "repository-context-evidence")
        self.assertTrue(validate_contract("context-evidence", item)["valid"])

    def test_same_content_is_proven_same(self):
        a = make_context_evidence(kind="symbol", path="a.py", symbol="f", start_line=1, end_line=2, revision="r1", content="return 1")
        b = make_context_evidence(kind="symbol", path="a.py", symbol="f", start_line=1, end_line=2, revision="r1", content="return 1")
        result = verify_context_evidence(a, b)
        self.assertEqual(result["status"], "proven-same")
        self.assertTrue(result["merge_authorized"])

    def test_same_location_different_revision_is_not_mergeable(self):
        a = make_context_evidence(kind="symbol", path="a.py", symbol="f", start_line=1, end_line=2, revision="r1")
        b = make_context_evidence(kind="symbol", path="a.py", symbol="f", start_line=1, end_line=2, revision="r2")
        result = verify_context_evidence(a, b)
        self.assertEqual(result["status"], "revision-conflict")
        self.assertFalse(result["merge_authorized"])

    def test_structured_assertion_conflict_is_preserved(self):
        a = make_context_evidence(kind="symbol", path="a.py", symbol="mode", revision="r1", assertion={"subject":"payment", "predicate":"mode", "value":"async"})
        b = make_context_evidence(kind="symbol", path="a.py", symbol="mode", revision="r1", assertion={"subject":"payment", "predicate":"mode", "value":"sync"})
        result = verify_context_evidence(a, b)
        self.assertEqual(result["status"], "conflict")
        self.assertFalse(result["merge_authorized"])


class V23ContextStoreTests(unittest.TestCase):
    def test_store_is_locator_only_and_has_active_recallable_tiers(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_repo(root)
            index = build_index(root)
            context = build_context(index, "checkout", budget=800, max_files=1, max_symbols=1, session="t")
            store = build_repository_context_store(index, context, session="t", persist=False)
            stats = store.stats()
            self.assertGreater(stats["counts"]["active"], 0)
            self.assertGreater(stats["counts"]["recallable"], 0)
            self.assertTrue(stats["locator_only"])
            self.assertFalse(stats["full_source_persisted"])
            self.assertTrue(all("content" not in item for item in store.items("recallable")))

    def test_refresh_context_demotes_old_hot_items(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_repo(root)
            index = build_index(root)
            c1 = build_context(index, "checkout", budget=800, max_files=1, max_symbols=1, session="t")
            s1 = build_repository_context_store(index, c1, session="t", persist=True)
            old_active = {x["id"] for x in s1.items("active")}
            c2 = build_context(index, "record_payment_event", budget=800, max_files=1, max_symbols=1, session="t2")
            # Same store session: c2 becomes authoritative HOT set.
            s2 = build_repository_context_store(index, c2, session="t", persist=False)
            new_active = {x["id"] for x in s2.items("active")}
            self.assertNotEqual(old_active, new_active)
            self.assertTrue(old_active - new_active)

    def test_stale_active_context_is_demoted(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_repo(root)
            index = build_index(root)
            context = build_context(index, "retry_payment", budget=800, max_files=1, max_symbols=2, session="s")
            store = build_repository_context_store(index, context, session="s", persist=False)
            self.assertTrue(any(x.get("path") == "payment.py" and x.get("tier") == "active" for x in store.items()))
            (root / "payment.py").write_text("def retry_payment():\n    return 'sync'\n", encoding="utf-8")
            result = invalidate_stale_context(store, persist=False)
            self.assertGreater(result["stale_items"], 0)
            self.assertGreater(result["active_items_demoted"], 0)
            self.assertFalse(any(x.get("path") == "payment.py" and x.get("tier") == "active" and x.get("validity") == "current" for x in store.items()))

    def test_missing_context_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_repo(root)
            index = build_index(root)
            context = build_context(index, "retry_payment", budget=800, max_files=1, max_symbols=2, session="s")
            store = build_repository_context_store(index, context, session="s", persist=False)
            (root / "payment.py").unlink()
            result = invalidate_stale_context(store, persist=False)
            self.assertGreater(result["missing_items"], 0)
            missing = [x for x in store.items() if x.get("path") == "payment.py"]
            self.assertTrue(missing)
            self.assertTrue(all(x["tier"] == "rejected" for x in missing))


class V23RecallTests(unittest.TestCase):
    def test_exact_symbol_recall_rehydrates_only_span(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_repo(root)
            index = build_index(root)
            context = build_context(index, "checkout", budget=800, max_files=1, max_symbols=1, session="s")
            store = build_repository_context_store(index, context, session="s", persist=False)
            result = recall_repository_context(index, "retry_payment", store=store, budget=400, top_k=2, persist=False)
            self.assertEqual(result["metrics"]["model_calls_added"], 0)
            evidence = result["model_payload"]["evidence"]
            self.assertTrue(any(x.get("symbol") == "retry_payment" for x in evidence))
            recalled = next(x for x in evidence if x.get("symbol") == "retry_payment")
            self.assertIn("def retry_payment", recalled["content"])
            self.assertNotIn("def charge", recalled["content"])
            self.assertTrue(validate_contract("recall-result", result)["valid"])

    def test_already_active_evidence_is_not_recalled_again(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_repo(root)
            index = build_index(root)
            context = build_context(index, "retry_payment", budget=1200, max_files=2, max_symbols=4, session="s")
            store = build_repository_context_store(index, context, session="s", persist=False)
            active_symbols = {x.get("symbol") for x in store.items("active")}
            self.assertIn("retry_payment", active_symbols)
            result = recall_repository_context(index, "retry_payment", store=store, budget=500, top_k=3, persist=False)
            self.assertFalse(any(x.get("symbol") == "retry_payment" for x in result["model_payload"]["evidence"]))

    def test_graph_neighbor_is_rerank_only_not_standalone_relevance(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_repo(root)
            index = build_index(root)
            context = build_context(index, "checkout", budget=500, max_files=1, max_symbols=1, session="s")
            store = build_repository_context_store(index, context, session="s", persist=False)
            result = recall_repository_context(index, "definitely-not-present-xyz", store=store, budget=400, top_k=6, persist=False)
            self.assertEqual(result["metrics"]["recalled_count"], 0)
            self.assertEqual(result["metrics"]["model_visible_tokens"], 0)
            self.assertEqual(result["metrics"]["model_calls_added"], 0)
            self.assertTrue(result["context_status"]["escalation_recommended"])

    def test_recall_budget_is_hard_bound(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_repo(root)
            index = build_index(root)
            store = build_repository_context_store(index, None, session="s", persist=False)
            result = recall_repository_context(index, "payment", store=store, budget=120, top_k=20, persist=False)
            self.assertLessEqual(result["metrics"]["model_visible_tokens"], 120)

    def test_model_context_keeps_store_in_sidecar_only(self):
        rich = {
            "files": [{"path":"a.py", "functions":["f"]}],
            "symbols": [], "external_context": [],
            "context_store": {"counts":{"active":1,"recallable":20}},
            "recall_policy": {"model_calls_added":0},
        }
        split = split_model_context(rich)
        text = json.dumps(split["model_payload"])
        self.assertNotIn("recallable", text)
        self.assertEqual(split["sidecar"]["context_store"]["counts"]["recallable"], 20)

    def test_recall_benchmark_can_improve_critical_evidence_recall_without_model_calls(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_repo(root)
            index = build_index(root)
            cases = [{
                "name":"hidden-retry",
                "task":"understand unrelated helper",
                "query":"retry_payment",
                "critical_evidence":[{"path":"payment.py","symbol":"retry_payment"}],
                "initial_budget":800, "max_files":1, "max_symbols":1,
            }]
            result = benchmark_context_recall(index, cases, recall_budget=500)
            agg = result["aggregate"]
            self.assertEqual(agg["model_calls_added_by_recall"], 0)
            self.assertGreaterEqual(agg["final_critical_evidence_recall"], agg["initial_critical_evidence_recall"])
            self.assertEqual(agg["final_critical_evidence_recall"], 1.0)
            self.assertTrue(validate_contract("recall-benchmark", result)["valid"])


class V23AdditionalSafetyTests(unittest.TestCase):
    def test_error_string_recall_uses_local_repository_search_and_drops_file_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "payment.py").write_text(
                "def retry_payment():\n    raise RuntimeError('PAYMENT_RETRY_EXHAUSTED')\n",
                encoding="utf-8",
            )
            index = build_index(root)
            store = build_repository_context_store(index, None, session="s", persist=False)
            result = recall_repository_context(index, "PAYMENT_RETRY_EXHAUSTED", store=store, budget=400, persist=False)
            self.assertTrue(result["sidecar"]["repository_search"]["used"])
            self.assertEqual(result["metrics"]["model_calls_added"], 0)
            self.assertGreaterEqual(result["metrics"]["cross_layer_duplicates_dropped"], 1)
            evidence = result["model_payload"]["evidence"]
            self.assertEqual(len(evidence), 1)
            self.assertEqual(evidence[0]["symbol"], "retry_payment")

    def test_context_store_does_not_duplicate_warm_index(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_repo(root)
            index = build_index(root)
            context = build_context(index, "checkout", budget=800, max_files=1, max_symbols=1, session="s")
            store = build_repository_context_store(index, context, session="s", persist=False)
            self.assertFalse(store.stats()["warm_locators_duplicated"])
            self.assertLess(len(store.data["items"]), store.data["index_summary"]["locator_count"])
            self.assertTrue(all(item.get("tier") in {"active", "rejected"} for item in store.items()))

    def test_rejected_tombstones_are_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); root.mkdir(exist_ok=True)
            store = RepositoryContextStore(root, "s")
            for i in range(1100):
                ev = make_context_evidence(kind="file", path=f"gone/{i}.py", revision="x", tier="active")
                store.reject_evidence(ev, reason="repository-path-missing", validity="missing")
            self.assertLessEqual(len(store.items("rejected")), 1000)

    def test_git_blob_revision_avoids_touch_only_false_stale(self):
        import os, subprocess
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_repo(root)
            subprocess.run(["git","init","-q"],cwd=root,check=True)
            subprocess.run(["git","config","user.email","test@example.com"],cwd=root,check=True)
            subprocess.run(["git","config","user.name","Test"],cwd=root,check=True)
            subprocess.run(["git","add","."],cwd=root,check=True)
            subprocess.run(["git","commit","-qm","init"],cwd=root,check=True)
            index = build_index(root)
            context = build_context(index, "retry_payment", budget=800, max_files=1, max_symbols=2, session="s")
            store = build_repository_context_store(index, context, session="s", persist=False)
            payment_active = [x for x in store.items("active") if x.get("path") == "payment.py"]
            self.assertTrue(payment_active)
            self.assertTrue(all((x.get("revision") or {}).get("kind") == "git-blob" for x in payment_active))
            os.utime(root / "payment.py", None)
            result = invalidate_stale_context(store, persist=False)
            self.assertEqual(result["stale_items"], 0)

    def test_context_sufficiency_gate_recommends_recall_without_model_call(self):
        status = assess_context_sufficiency({"files": [], "symbols": [], "external_context": [], "coverage": {"score": 0.1}})
        self.assertFalse(status["sufficient"])
        self.assertEqual(status["recommended_action"], "recall")
        self.assertEqual(status["model_calls_added"], 0)


class V23ScopeAndCliTests(unittest.TestCase):
    def test_runtime_remains_native_but_is_not_core(self):
        self.assertIn("runtime.sandbox", NATIVE_CAPABILITIES)
        self.assertNotIn("runtime.sandbox", CORE_CAPABILITIES)
        self.assertIn("runtime.sandbox", ADVISORY_CAPABILITIES)
        self.assertIn("context.recall", CORE_CAPABILITIES)
        self.assertIn("quality.recall-benchmark", CORE_CAPABILITIES)

    def test_new_schemas_exposed(self):
        names = {x["name"] for x in list_schemas()}
        self.assertTrue({"context-evidence", "context-store", "recall-result", "recall-benchmark"}.issubset(names))
        self.assertGreaterEqual(len(names), 30)

    def test_recall_cli(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); make_repo(root)
            out=io.StringIO(); err=io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc=main(["recall","retry_payment","--repo",td,"--budget","500","--pretty"])
            self.assertEqual(rc,0,err.getvalue())
            payload=json.loads(out.getvalue())
            self.assertEqual(payload["schema"],"repo-context-recall-result/v1")
            self.assertEqual(payload["metrics"]["model_calls_added"],0)

    def test_context_store_cli_status(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); make_repo(root)
            out=io.StringIO(); err=io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(["context-store","rebuild","--repo",td]),0)
            out=io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(["context-store","status","--repo",td]),0)
            payload=json.loads(out.getvalue())
            self.assertTrue(payload["store"]["locator_only"])


class V23RecallHydrationTests(unittest.TestCase):
    def test_module_level_text_hit_rehydrates_bounded_snippet_not_whole_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            lines = [
                "PAYMENT_PROVIDER_UNAVAILABLE = 'provider unavailable'",
                "",
                "def helper():",
                "    return 1",
            ] + [f"PADDING_{i} = {i}" for i in range(30)]
            (root / "constants.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
            index = build_index(root)
            store = build_repository_context_store(index, None, session="s", persist=False)
            result = recall_repository_context(
                index, "PAYMENT_PROVIDER_UNAVAILABLE",
                store=store, budget=400, top_k=2, persist=False,
            )
            evidence = result["model_payload"]["evidence"]
            file_ev = next(x for x in evidence if x.get("path") == "constants.py" and x.get("kind") == "file")
            self.assertEqual(file_ev.get("content_mode"), "search-snippet")
            self.assertIn("PAYMENT_PROVIDER_UNAVAILABLE", file_ev.get("content", ""))
            self.assertLessEqual(len(file_ev.get("content", "").splitlines()), 5)
            self.assertNotIn("PADDING_29", file_ev.get("content", ""))
            self.assertEqual(result["metrics"]["model_calls_added"], 0)


    def test_recreated_repository_evidence_clears_missing_tombstone_on_recall(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            target = root / "recover.py"
            target.write_text("def recovered_symbol():\n    return 1\n", encoding="utf-8")
            index1 = build_index(root)
            context = build_context(index1, "recovered_symbol", budget=500, max_files=1, max_symbols=2, session="s")
            store = build_repository_context_store(index1, context, session="s", persist=False)
            target.unlink()
            missing = invalidate_stale_context(store, persist=False)
            self.assertGreaterEqual(missing["missing_items"], 1)
            self.assertTrue(store.items("rejected"))

            target.write_text("def recovered_symbol():\n    return 2\n", encoding="utf-8")
            index2 = build_index(root)
            result = recall_repository_context(index2, "recovered_symbol", store=store, budget=300, persist=False)
            self.assertGreaterEqual(result["sidecar"]["index_reconciliation"]["resurrected_tombstones"], 1)
            self.assertTrue(any(x.get("symbol") == "recovered_symbol" for x in result["model_payload"]["evidence"]))
            self.assertEqual(result["metrics"]["model_calls_added"], 0)

    def test_context_store_state_is_recognized_regenerable_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); make_repo(root)
            index = build_index(root)
            context = build_context(index, "checkout", budget=800, max_files=1, max_symbols=1, session="s")
            build_repository_context_store(index, context, session="s", persist=True)
            inventory = state_inventory(root)
            names = {x["name"] for x in inventory["regenerable"]}
            unknown = {x["name"] for x in inventory["unrecognized"]}
            self.assertIn("context-stores", names)
            self.assertNotIn("context-stores", unknown)


if __name__ == "__main__":
    unittest.main()
