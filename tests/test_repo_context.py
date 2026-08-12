import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("repo_context", ROOT / "scripts" / "repo_context.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class RepoContextTests(unittest.TestCase):
    def test_scan_sample_project(self):
        result = MOD.scan_repository(ROOT / "examples" / "sample-project")
        self.assertGreaterEqual(result["project"]["files_scanned"], 3)
        self.assertIn("JavaScript", result["project"]["languages"])
        self.assertTrue(any(x.endswith("src/index.js") for x in result["entry_points"]))
        self.assertTrue(result["important_files"])

    def test_ignores_noise_directories(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "src").mkdir()
            (root / "node_modules" / "pkg").mkdir(parents=True)
            (root / "src" / "main.py").write_text("def main():\n    pass\n", encoding="utf-8")
            (root / "node_modules" / "pkg" / "x.js").write_text("export const x = 1", encoding="utf-8")
            result = MOD.scan_repository(root)
            paths = {f["path"] for f in result["files"]}
            self.assertIn("src/main.py", paths)
            self.assertFalse(any("node_modules" in p for p in paths))

    def test_extracts_symbols(self):
        text = "class Demo:\n    def run(self, x):\n        return x\n"
        summary = MOD.summarize_source("demo.py", text)
        self.assertIn("Demo", summary["classes"])
        self.assertTrue(any("run" in f for f in summary["functions"]))


if __name__ == "__main__":
    unittest.main()
