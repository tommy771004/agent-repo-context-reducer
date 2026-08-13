"""Regression tests for the language tiers documented in README "Supported Languages".

These lock the extraction contract per language so the documented tier table cannot
silently drift away from what the parsers actually produce.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from repo_context.cache import CACHE_VERSION, SummaryCache
from repo_context.parsers import summarize_source
from repo_context.scanner import build_index
from repo_context.symbols import extract_symbol_index, read_symbol

C_SOURCE = """#include <stdio.h>
#include "local.h"
/* block comment */
int add(int a, int b) { return a + b; }
static void run(void) { printf("x"); }
"""

SHELL_SOURCE = """#!/usr/bin/env bash
# a comment
source ./lib.sh
deploy() {
  echo hi
}
function rollback {
  echo no
}
"""

PS_SOURCE = """Import-Module Az
. .\\helper.ps1
function Get-Order {
  param($id)
  return $id
}
"""

SQL_SOURCE = """CREATE TABLE orders (id INT PRIMARY KEY);
create view paid AS
SELECT * FROM orders;
CREATE OR REPLACE PROCEDURE settle_all()
BEGIN
  UPDATE orders SET id = 1;
END;
"""


class LanguageExtractionTests(unittest.TestCase):
    def test_c_extracts_includes_and_definitions(self):
        s = summarize_source("main.c", C_SOURCE)
        # Quoted includes become project-local specs; angle includes stay external.
        self.assertIn("./local.h", s["imports"])
        self.assertIn("stdio.h", s["imports"])
        self.assertIn("add(int a, int b)", s["functions"])
        self.assertIn("run", s["symbols"])

    def test_c_ignores_control_flow_and_declarations(self):
        s = summarize_source("x.c", "int f(void) {\n  if (a) { return 1; }\n  while (b) { }\n}\nint g(int a);\n")
        names = {fn.split("(")[0] for fn in s["functions"]}
        self.assertIn("f", names)
        self.assertNotIn("if", names)
        self.assertNotIn("while", names)
        # A prototype without a body is a declaration, not a definition.
        self.assertNotIn("g", names)

    def test_shell_extracts_sourced_files_and_both_function_forms(self):
        s = summarize_source("deploy.sh", SHELL_SOURCE)
        self.assertIn("./lib.sh", s["imports"])
        names = {fn.split("(")[0] for fn in s["functions"]}
        self.assertEqual({"deploy", "rollback"}, names)

    def test_shell_comment_lines_are_still_ignored(self):
        s = summarize_source("x.sh", "# source ./not-real.sh\necho hi\n")
        self.assertEqual([], s["imports"])

    def test_powershell_extracts_modules_dot_sourcing_and_hyphenated_names(self):
        s = summarize_source("run.ps1", PS_SOURCE)
        self.assertIn("Az", s["imports"])
        # Backslash dot-source paths are normalized so the graph can resolve them.
        self.assertIn("./helper.ps1", s["imports"])
        self.assertIn("Get-Order", s["symbols"])

    def test_sql_extracts_objects_case_insensitively(self):
        s = summarize_source("schema.sql", SQL_SOURCE)
        self.assertIn("orders", s["types"])
        self.assertIn("paid", s["types"])
        self.assertIn("settle_all()", s["functions"])


class SymbolReadingTests(unittest.TestCase):
    def _read(self, name: str, source: str, symbol: str) -> dict:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / name).write_text(source, encoding="utf-8")
            return read_symbol(root, name, symbol)

    def test_symbol_reading_works_for_every_newly_supported_language(self):
        cases = [
            ("main.c", C_SOURCE, "add", "int add"),
            ("deploy.sh", SHELL_SOURCE, "deploy", "echo hi"),
            ("deploy.sh", SHELL_SOURCE, "rollback", "echo no"),
            ("run.ps1", PS_SOURCE, "Get-Order", "param($id)"),
            ("schema.sql", SQL_SOURCE, "orders", "CREATE TABLE orders"),
        ]
        for name, source, symbol, expected in cases:
            with self.subTest(symbol=symbol):
                result = self._read(name, source, symbol)
                self.assertIn(expected, result["content"])
                self.assertGreaterEqual(result["end_line"], result["start_line"])

    def test_existing_languages_keep_their_symbol_behavior(self):
        js = "export function handler(req) {\n  return 1;\n}\n"
        self.assertEqual(["handler"], [s["name"] for s in extract_symbol_index("a.js", js)])
        py = "def charge(amount):\n    return amount\n"
        self.assertEqual(["charge"], [s["name"] for s in extract_symbol_index("a.py", py)])


class DependencyEdgeTests(unittest.TestCase):
    def test_c_shell_and_powershell_produce_local_graph_edges(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "local.h").write_text("int add(int a, int b);\n", encoding="utf-8")
            (root / "main.c").write_text(C_SOURCE, encoding="utf-8")
            (root / "lib.sh").write_text("echo lib\n", encoding="utf-8")
            (root / "deploy.sh").write_text(SHELL_SOURCE, encoding="utf-8")
            (root / "helper.ps1").write_text("Write-Host x\n", encoding="utf-8")
            (root / "run.ps1").write_text(PS_SOURCE, encoding="utf-8")

            index = build_index(root, use_cache=False)
            edges = index["graph"]["edges"]
            self.assertIn("local.h", edges.get("main.c", []))
            self.assertIn("lib.sh", edges.get("deploy.sh", []))
            self.assertIn("helper.ps1", edges.get("run.ps1", []))
            # System headers and installed modules must not become local edges.
            self.assertIn("stdio.h", index["graph"]["external"].get("main.c", []))


class CacheVersioningTests(unittest.TestCase):
    def test_stale_parser_generation_caches_are_discarded_not_reused(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            legacy_dir = root / ".repo-context" / "cache"
            legacy_dir.mkdir(parents=True)
            # A summary produced by the previous parser generation, for a file that never changes.
            (legacy_dir / "summaries-v3.json").write_text(
                '{"version":3,"items":{"main.c":{"key":"stale","summary":{"imports":[],"functions":[]}}}}',
                encoding="utf-8",
            )
            cache = SummaryCache(root, enabled=True)
            self.assertEqual(CACHE_VERSION, cache.data["version"])
            self.assertEqual({}, cache.data["items"], "a previous-generation cache must not be reused")

            cache.put("main.c", "k", {"imports": ["./local.h"]})
            cache.save()
            self.assertFalse((legacy_dir / "summaries-v3.json").exists(), "stale cache file should be removed")
            self.assertTrue((legacy_dir / f"summaries-v{CACHE_VERSION}.json").is_file())


if __name__ == "__main__":
    unittest.main()
