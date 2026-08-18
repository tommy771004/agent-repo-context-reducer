from __future__ import annotations

import contextlib
import io
import json
import pathlib
import subprocess
import tempfile
import unittest

from repo_context import __version__
from repo_context.candidate_detection import (
    analyze_candidates,
    register_candidate_provider,
    verify_candidate,
)
from repo_context.capabilities import NATIVE_CAPABILITIES
from repo_context.cli import main
from repo_context.context_planner import build_context
from repo_context.fan_in import reduce_worker_outputs, reduce_worker_stream
from repo_context.git_provenance import file_provenance, repository_provenance
from repo_context.scanner import build_index
from repo_context.schema_registry import list_schemas, validate_contract
from repo_context.synthesis_packet import build_synthesis_packet
from repo_context.tokenizer import (
    count_tokens,
    register_tokenizer,
    token_estimate,
    tokenizer_status,
    unregister_tokenizer,
)


class VersionAndContractTests(unittest.TestCase):
    def test_version_is_v17(self):
        self.assertGreaterEqual(tuple(int(x) for x in __version__.split(".")[:2]), (1, 7))

    def test_v17_schemas_are_registered(self):
        names = {item["name"] for item in list_schemas()}
        self.assertTrue({"token-estimate", "provenance", "candidate-analysis"} <= names)

    def test_v17_capabilities_are_declared(self):
        expected = {
            "context.streaming",
            "context.tokenizer",
            "context.candidate-detection",
            "context.deterministic-verifier",
            "context.git-provenance",
        }
        self.assertTrue(expected <= NATIVE_CAPABILITIES)


class StreamingFanInTests(unittest.TestCase):
    def _record(self, worker: str, claim: str = "payment async") -> dict:
        return {
            "worker_id": worker,
            "findings": [{"claim": claim, "evidence": "queue", "source": f"{worker}.py", "canonicalKey": "payment|mode"}],
        }

    def test_streaming_matches_list_reducer_for_core_counts(self):
        records = [self._record("a"), self._record("b")]
        listed = reduce_worker_outputs(records)
        streamed = reduce_worker_stream(iter(records))
        for key in ("output_finding_count", "duplicate_count", "agreement_group_count"):
            self.assertEqual(listed["stats"][key], streamed["stats"][key])
        self.assertFalse(listed["stats"]["streaming"])
        self.assertTrue(streamed["stats"]["streaming"])

    def test_streaming_retains_groups_not_raw_documents(self):
        def records():
            for i in range(2000):
                yield self._record(f"w{i}")
        result = reduce_worker_stream(records())
        self.assertEqual(result["stats"]["worker_output_count"], 2000)
        self.assertEqual(result["stats"]["output_finding_count"], 1)
        self.assertEqual(result["stats"]["peak_reducer_group_count"], 1)
        self.assertEqual(result["findings"][0]["reducer"]["agreement_count"], 2000)

    def test_streaming_malformed_details_are_bounded(self):
        result = reduce_worker_stream(({"worker": f"w{i}", "findings": [{}]} for i in range(50)), malformed_detail_limit=5)
        self.assertEqual(result["stats"]["malformed_count"], 50)
        self.assertEqual(result["stats"]["malformed_details_retained"], 5)
        self.assertEqual(len(result["malformed"]), 5)

    def test_main_cli_reads_ndjson_incrementally(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "workers.ndjson"
            path.write_text("\n".join(json.dumps(self._record(w)) for w in ("a", "b")) + "\n", encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["fan-in", str(path), "--format", "ndjson", "--budget", "5000"])
            self.assertEqual(rc, 0)
            data = json.loads(out.getvalue())
            self.assertTrue(data["input"]["streaming"])
            self.assertTrue(data["reduction"]["stats"]["streaming"])


class TokenizerTests(unittest.TestCase):
    def test_native_tokenizer_is_dependency_free_fallback(self):
        estimate = token_estimate("abcd")
        self.assertEqual(estimate["tokenizer"], "native")
        self.assertFalse(estimate["exact"])
        self.assertEqual(estimate["tokens"], 1)

    def test_host_registered_tokenizer_drives_reducer_and_packet_budget(self):
        register_tokenizer("unit-test-exact", lambda text: len(text.split()), exact=True)
        try:
            workers = [{"worker": "a", "findings": [{"claim": "one two", "evidence": "three", "source": "a.py"}]}]
            reduction = reduce_worker_outputs(workers, tokenizer="unit-test-exact")
            self.assertEqual(reduction["stats"]["tokenizer"], "unit-test-exact")
            self.assertTrue(reduction["stats"]["tokenizer_exact"])
            packet = build_synthesis_packet(reduction, max_estimated_tokens=200, tokenizer="unit-test-exact")
            self.assertEqual(packet["budget"]["tokenizer"], "unit-test-exact")
            self.assertTrue(packet["budget"]["tokenizer_exact"])
        finally:
            unregister_tokenizer("unit-test-exact")

    def test_tiktoken_is_reported_as_optional_not_assumed(self):
        status = {item["name"]: item for item in tokenizer_status()}
        self.assertIn("tiktoken", status)
        self.assertEqual(status["tiktoken"]["source"], "optional-package")

    def test_cli_tokenizer_estimate(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(["tokenizer", "estimate", "hello world"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue())["tokenizer"], "native")


class CandidateVerificationTests(unittest.TestCase):
    def test_similarity_never_authorizes_merge_without_identity(self):
        findings = [
            {"claim": "Revenue increased 20%", "evidence": "a", "source": "a"},
            {"claim": "Revenue did not increase 20%", "evidence": "b", "source": "b"},
        ]
        result = analyze_candidates(findings, threshold=0.5)
        self.assertTrue(result["pairs"])
        self.assertFalse(result["pairs"][0]["verification"]["merge_authorized"])
        self.assertFalse(result["semantic_similarity_used"])

    def test_exact_structured_identity_and_side_can_authorize_candidate_merge(self):
        a = {"claim": "payment mode async", "canonicalKey": "payment|mode", "value": 1}
        b = {"claim": "async payment status", "canonicalKey": "payment|mode", "value": 1}
        verdict = verify_candidate(a, b)
        self.assertEqual(verdict["verdict"], "safe-duplicate")
        self.assertTrue(verdict["merge_authorized"])

    def test_exact_identity_with_different_side_is_contradiction_candidate(self):
        a = {"claim": "payment sync", "canonicalKey": "payment|mode", "value": 1}
        b = {"claim": "payment async", "canonicalKey": "payment|mode", "value": 2}
        verdict = verify_candidate(a, b)
        self.assertFalse(verdict["merge_authorized"])
        self.assertTrue(verdict["contradiction_candidate"])

    def test_host_semantic_provider_is_candidate_only(self):
        register_candidate_provider("unit-semantic", lambda findings, threshold, max_pairs: [(0, 1, 0.99)], semantic=True)
        findings = [
            {"claim": "alpha", "evidence": "a", "source": "a"},
            {"claim": "beta", "evidence": "b", "source": "b"},
        ]
        result = analyze_candidates(findings, provider="unit-semantic")
        self.assertTrue(result["semantic_similarity_used"])
        self.assertFalse(result["pairs"][0]["verification"]["merge_authorized"])

    def test_fan_in_candidate_analysis_does_not_change_output_count(self):
        workers = [
            {"worker": "a", "findings": [{"claim": "Revenue increased 20%", "evidence": "a", "source": "a"}]},
            {"worker": "b", "findings": [{"claim": "Revenue did not increase 20%", "evidence": "b", "source": "b"}]},
        ]
        result = reduce_worker_outputs(workers, candidate_provider="lexical", candidate_threshold=0.5)
        self.assertEqual(result["stats"]["output_finding_count"], 2)
        self.assertFalse(result["provenance"]["candidate_similarity_merge_authority"])


@unittest.skipUnless(subprocess.run(["git", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0, "git required")
class GitProvenanceTests(unittest.TestCase):
    def _repo(self, td: str) -> pathlib.Path:
        root = pathlib.Path(td)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
        (root / "payment.py").write_text("def charge(amount):\n    return amount\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)
        return root

    def test_file_provenance_distinguishes_head_and_dirty_worktree(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(td)
            clean = file_provenance(root, "payment.py")
            self.assertTrue(clean["tracked"])
            self.assertFalse(clean["dirty"])
            self.assertEqual(clean["content_identity"]["blob_sha"], clean["head_blob_sha"])
            (root / "payment.py").write_text("def charge(amount):\n    return amount + 1\n", encoding="utf-8")
            dirty = file_provenance(root, "payment.py")
            self.assertTrue(dirty["dirty"])
            self.assertNotEqual(dirty["working_blob_sha"], dirty["head_blob_sha"])
            self.assertEqual(dirty["content_identity"]["source"], "working-tree")

    def test_context_pack_carries_repository_and_file_git_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(td)
            index = build_index(root, use_cache=False)
            pack = build_context(index, "payment charge", budget=1600, session="prov")
            self.assertTrue(pack["repository_provenance"]["git_available"])
            self.assertEqual(pack["repository_provenance"]["commit"], repository_provenance(root)["commit"])
            self.assertTrue(pack["files"])
            self.assertIn("git", pack["files"][0]["provenance"])
            if pack["symbols"]:
                self.assertIn("git", pack["symbols"][0]["provenance"])

    def test_cli_provenance_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(td)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["provenance", "file", td, "payment.py"])
            self.assertEqual(rc, 0)
            data = json.loads(out.getvalue())
            self.assertTrue(data["tracked"])
            self.assertTrue(validate_contract("provenance", data)["valid"])


if __name__ == "__main__":
    unittest.main()
