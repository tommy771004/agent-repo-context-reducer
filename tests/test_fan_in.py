from __future__ import annotations

import unittest

from repo_context.fan_in import reduce_worker_outputs
from repo_context.synthesis_packet import build_synthesis_packet
from repo_context.handoff import reduce_handoff


class FanInTests(unittest.TestCase):
    def test_exact_canonical_dedupe_preserves_agreement(self):
        result = reduce_worker_outputs([
            {"worker": "a", "findings": [
                {"claim": "Payment is async", "evidence": "payment.py:10", "source": "payment.py",
                 "confidence": 0.9, "canonicalKey": "payment|async"}
            ]},
            {"worker": "b", "findings": [
                {"claim": "Payment update is asynchronous", "evidence": "order.py:20", "source": "order.py",
                 "confidence": 0.8, "canonicalKey": "payment|async"}
            ]},
        ], unstructured_canonical_policy="legacy-merge")
        self.assertEqual(result["stats"]["output_finding_count"], 1)
        self.assertEqual(result["stats"]["duplicate_count"], 1)
        self.assertEqual(result["findings"][0]["reducer"]["agreement_count"], 2)
        self.assertEqual(result["findings"][0]["reducer"]["supporting_sources"], ["order.py", "payment.py"])

    def test_malformed_is_logged_not_silently_absorbed(self):
        result = reduce_worker_outputs([
            {"worker": "a", "findings": [
                {"claim": "x", "source": "a.py"}
            ]}
        ])
        self.assertEqual(result["stats"]["valid_finding_count"], 0)
        self.assertEqual(result["stats"]["malformed_count"], 1)
        self.assertIn("evidence", result["malformed"][0]["reason"])

    def test_structured_contradiction_is_surfaced(self):
        base = {
            "subject": "payment", "predicate": "mode", "period": "current",
            "canonicalKey": "payment|mode", "evidence": "code", "unit": "",
        }
        result = reduce_worker_outputs([
            {"worker": "a", "findings": [{**base, "claim": "sync", "source": "a.py", "value": 1}]},
            {"worker": "b", "findings": [{**base, "claim": "async", "source": "b.py", "value": 2}]},
        ])
        self.assertEqual(result["stats"]["contradiction_count"], 1)
        self.assertEqual(result["contradictions"][0]["reasons"], ["value disagreement"])

    def test_similar_opposite_claims_are_not_fuzzy_merged(self):
        result = reduce_worker_outputs([
            {"worker": "a", "findings": [
                {"claim": "Revenue increased 20%", "evidence": "e1", "source": "s1"}
            ]},
            {"worker": "b", "findings": [
                {"claim": "Revenue did not increase 20%", "evidence": "e2", "source": "s2"}
            ]},
        ])
        self.assertEqual(result["stats"]["output_finding_count"], 2)
        self.assertFalse(result["provenance"]["semantic_similarity_used"])

    def test_synthesis_budget_keeps_high_confidence_first(self):
        findings = []
        for i, confidence in enumerate([0.95, 0.8, 0.6, 0.4]):
            findings.append({
                "claim": f"finding {i} " + ("x" * 300),
                "evidence": "e" * 300,
                "source": f"s{i}",
                "confidence": confidence,
                "reducer": {"agreement_count": 1},
            })
        reduction = {
            "findings": findings,
            "contradictions": [],
            "stats": {"worker_output_count": 4, "valid_finding_count": 4},
        }
        packet = build_synthesis_packet(reduction, max_estimated_tokens=500)
        selected = packet["findings"]
        self.assertTrue(selected)
        self.assertEqual(selected[0]["confidence"], 0.95)
        self.assertGreater(packet["budget"]["dropped_findings"], 0)
        self.assertFalse(packet["budget"]["overflow"])

    def test_contradictions_are_never_dropped_to_fake_budget_success(self):
        reduction = {
            "findings": [{"claim": "x", "evidence": "e", "source": "s", "confidence": 0.9}],
            "contradictions": [{
                "key": "k",
                "reasons": ["value disagreement"],
                "claims": [{"claim": "a" + "x" * 1200}, {"claim": "b" + "y" * 1200}],
            }],
            "stats": {"worker_output_count": 2, "contradiction_count": 1},
        }
        packet = build_synthesis_packet(reduction, max_estimated_tokens=120)
        self.assertTrue(packet["contradictions"])
        self.assertTrue(packet["budget"]["overflow"])
        self.assertEqual(packet["budget"]["dropped_findings"], 1)

    def test_handoff_token_budget_preserves_risks(self):
        payload = {
            "summary": "done",
            "evidence": ["x" * 800, "y" * 800],
            "targets": ["a.py", "b.py"],
            "tests": ["unit"],
            "risks": ["migration can corrupt data"],
            "debug_log": "z" * 10000,
        }
        result = reduce_handoff(
            payload, from_role="worker", to_role="grader",
            token_budget=220, preserve_fields=("summary", "tests", "risks")
        )
        self.assertIn("risks", result["handoff"])
        self.assertIn("tests", result["handoff"])
        self.assertNotIn("debug_log", result["handoff"])
        self.assertIn("budget", result)


if __name__ == "__main__":
    unittest.main()
