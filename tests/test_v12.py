from __future__ import annotations

import contextlib
import io
import json
import pathlib
import tempfile
import unittest

from repo_context.cli import main


class V12CliTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(argv)
        return rc, json.loads(out.getvalue())

    def test_cli_complexity(self):
        rc, data = self._run(["complexity", "explain this function"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["recommended_agents"], 1)
        self.assertEqual(data["classification"], "heuristic")

    def test_cli_plan_does_not_fake_executor_provider(self):
        with tempfile.TemporaryDirectory() as td:
            rc, data = self._run([
                "plan",
                "Autonomously implement an end-to-end migration across the entire project and ship production-ready integration",
                "--repo", td,
            ])
            self.assertEqual(rc, 0)
            self.assertIsNone(data["provider_layers"]["executor"]["executor.autonomous"])

    def test_cli_handoff_can_store_raw_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "planner.json"
            src.write_text(json.dumps({"summary": "ok", "decisions": ["use queue"], "noise": "x" * 5000}), encoding="utf-8")
            rc, data = self._run(["handoff", "planner", "implementer", str(src), "--repo", td, "--store-artifact"])
            self.assertEqual(rc, 0)
            self.assertTrue(data["artifact_id"])
            self.assertEqual(data["handoff"]["summary"], "ok")
            self.assertTrue((pathlib.Path(td) / ".repo-context" / "artifacts").is_dir())

    def test_cli_knowledge_search_uses_local_docs_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "docs").mkdir()
            (root / "docs" / "adr.md").write_text("# Queue decision\nUse event queue for payment updates.", encoding="utf-8")
            rc, data = self._run(["knowledge", "search", "payment event queue", "--repo", td])
            self.assertEqual(rc, 0)
            self.assertEqual(data["classification"], "deterministic-lexical-knowledge-search")
            self.assertEqual(data["results"][0]["path"], "docs/adr.md")


if __name__ == "__main__":
    unittest.main()
