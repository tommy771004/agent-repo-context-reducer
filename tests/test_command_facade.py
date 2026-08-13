from __future__ import annotations

import contextlib
import io
import json
import pathlib
import tempfile
import unittest

from repo_context.cli import main
from repo_context.command_facade import FACADES, get_facade
from repo_context.host_adapters import install_host_commands, host_status
from repo_context.router import route_task


class CommandFacadeTests(unittest.TestCase):
    def test_all_short_commands_use_reducer_prefix(self):
        self.assertEqual(len(FACADES), 5)
        self.assertTrue(all(name.startswith("reducer-") for name in FACADES))

    def test_debug_facade_forces_debug_route(self):
        routed = route_task("explain project architecture", forced_type=get_facade("reducer-debug").intent)
        self.assertEqual(routed["task_type"], "debug")
        self.assertEqual(routed["classification"], "explicit")

    def test_impact_facade_forces_change_impact(self):
        routed = route_task("tell me about architecture", forced_type=get_facade("reducer-impact").intent)
        self.assertEqual(routed["task_type"], "change-impact")

    def test_claude_host_install_creates_five_slash_commands(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            result = install_host_commands(root, "claude-code", scope="project")
            self.assertEqual(len(result["written"]), 5)
            self.assertTrue((root / ".claude" / "commands" / "reducer-debug.md").is_file())
            text = (root / ".claude" / "commands" / "reducer-debug.md").read_text(encoding="utf-8")
            self.assertIn("run reducer-debug", text)
            self.assertIn("$ARGUMENTS", text)
            self.assertTrue(host_status(root, "claude-code")["all_installed"])

    def test_codex_host_install_creates_named_skills(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            result = install_host_commands(root, "codex", scope="project")
            self.assertEqual(len(result["written"]), 5)
            skill = root / ".agents" / "skills" / "reducer-review" / "SKILL.md"
            self.assertTrue(skill.is_file())
            text = skill.read_text(encoding="utf-8")
            self.assertIn("name: reducer-review", text)
            self.assertIn("run reducer-review", text)

    def test_cli_commands_lists_facades(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(["commands"])
        self.assertEqual(rc, 0)
        data = json.loads(out.getvalue())
        names = {x["name"] for x in data["commands"]}
        self.assertIn("reducer-repo", names)
        self.assertIn("reducer-doctor", names)

    def test_cli_debug_facade_forces_explicit_debug_workflow(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["run", "reducer-debug", "explain project architecture", "--repo", td, "--budget", "900"])
            self.assertEqual(rc, 0)
            data = json.loads(out.getvalue())
            self.assertEqual(data["route"]["task_type"], "debug")
            self.assertEqual(data["route"]["classification"], "explicit")

    def test_reducer_doctor_facade_maps_to_doctor(self):
        with tempfile.TemporaryDirectory() as td:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["run", "reducer-doctor", "--repo", td])
            self.assertEqual(rc, 0)
            data = json.loads(out.getvalue())
            self.assertIn("providers", data)


if __name__ == "__main__":
    unittest.main()
