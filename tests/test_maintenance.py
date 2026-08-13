"""Tests for the `update` / `remove` maintenance surface.

These lock the destructive-safety contract: dry run by default, user configuration and
user data preserved unless explicitly requested, and hand-edited shortcuts kept unless
forced.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from repo_context.artifact_store import ArtifactStore
from repo_context.cli import main
from repo_context.command_facade import FACADES
from repo_context.host_adapters import install_host_commands, host_status, uninstall_host_commands
from repo_context.indexer import build_persistent
from repo_context.maintenance import (
    PRESERVED_STATE, REGENERABLE_STATE, remove_state, self_update_hint, state_inventory,
    update_shortcuts,
)


def _seed(root: pathlib.Path) -> None:
    (root / "main.py").write_text("import os\ndef main():\n    return 1\n", encoding="utf-8")


def _seed_full_state(root: pathlib.Path) -> None:
    _seed(root)
    build_persistent(root, use_cache=True)
    ArtifactStore(root).put({"k": "v"}, producer="tester")
    (root / ".repo-context" / "providers.d").mkdir(parents=True, exist_ok=True)
    (root / ".repo-context" / "providers.d" / "mine.json").write_text('{"schema":"x"}', encoding="utf-8")
    (root / ".repo-context" / "config.json").write_text('{"trusted":["some-provider"]}', encoding="utf-8")


class StateRemovalTests(unittest.TestCase):
    def test_regenerable_and_preserved_sets_do_not_overlap(self):
        self.assertFalse(set(REGENERABLE_STATE) & set(PRESERVED_STATE))

    def test_dry_run_is_the_default_and_removes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _seed_full_state(root)
            result = remove_state(root)
            self.assertTrue(result["dry_run"])
            self.assertEqual([], result["removed"])
            self.assertTrue(result["planned"])
            self.assertTrue((root / ".repo-context" / "index.json").is_file())

    def test_user_configuration_and_data_survive_a_default_removal(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _seed_full_state(root)
            remove_state(root, yes=True)
            state = root / ".repo-context"
            # Regenerable state is gone.
            self.assertFalse((state / "index.json").exists())
            self.assertFalse((state / "cache").exists())
            # Provider trust, manifests and artifacts are not reproducible by re-scanning.
            self.assertTrue((state / "config.json").is_file())
            self.assertTrue((state / "providers.d" / "mine.json").is_file())
            self.assertTrue((state / "artifacts").is_dir())

    def test_all_flag_removes_user_data_too(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _seed_full_state(root)
            remove_state(root, yes=True, include_preserved=True)
            self.assertFalse((root / ".repo-context").exists())

    def test_inventory_separates_regenerable_from_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _seed_full_state(root)
            inv = state_inventory(root)
            names = {e["name"] for e in inv["regenerable"]}
            preserved = {e["name"] for e in inv["preserved"]}
            self.assertIn("index.json", names)
            self.assertIn("config.json", preserved)
            self.assertIn("artifacts", preserved)
            self.assertGreater(inv["regenerable_bytes"], 0)


class ShortcutRemovalTests(unittest.TestCase):
    def test_uninstall_roundtrip_removes_every_generated_shortcut(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            install_host_commands(root, "claude-code", scope="project")
            self.assertTrue(host_status(root, "claude-code")["all_installed"])
            result = uninstall_host_commands(root, "claude-code", scope="project", yes=True)
            self.assertEqual(len(FACADES), len(result["removed"]))
            self.assertFalse(host_status(root, "claude-code")["all_installed"])

    def test_uninstall_is_dry_run_without_yes(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            install_host_commands(root, "claude-code", scope="project")
            result = uninstall_host_commands(root, "claude-code", scope="project")
            self.assertTrue(result["dry_run"])
            self.assertEqual([], result["removed"])
            self.assertTrue(host_status(root, "claude-code")["all_installed"])

    def test_hand_edited_shortcuts_are_kept_unless_forced(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            install_host_commands(root, "claude-code", scope="project")
            edited = root / ".claude" / "commands" / "reducer-debug.md"
            edited.write_text(edited.read_text(encoding="utf-8") + "\nuser note\n", encoding="utf-8")

            result = uninstall_host_commands(root, "claude-code", scope="project", yes=True)
            self.assertIn("reducer-debug", result["skipped_modified"])
            self.assertTrue(edited.is_file())

            forced = uninstall_host_commands(root, "claude-code", scope="project", yes=True, force=True)
            self.assertEqual(1, len(forced["removed"]))
            self.assertFalse(edited.exists())

    def test_codex_skill_directories_are_cleaned_up(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            install_host_commands(root, "codex", scope="project")
            uninstall_host_commands(root, "codex", scope="project", yes=True)
            self.assertFalse((root / ".agents" / "skills" / "reducer-repo").exists())

    def test_uninstall_only_touches_known_facade_names(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            install_host_commands(root, "claude-code", scope="project")
            bystander = root / ".claude" / "commands" / "my-own-command.md"
            bystander.write_text("mine\n", encoding="utf-8")
            uninstall_host_commands(root, "claude-code", scope="project", yes=True, force=True)
            self.assertTrue(bystander.is_file(), "unrelated commands must never be removed")


class UpdateTests(unittest.TestCase):
    def test_update_shortcuts_does_not_install_where_nothing_was_installed(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            result = update_shortcuts(root, scopes=("project",))
            self.assertTrue(all(r["action"] == "skipped" for r in result["results"]))
            self.assertFalse((root / ".claude").exists())

    def test_update_shortcuts_re_renders_installed_shortcuts(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            install_host_commands(root, "claude-code", scope="project")
            target = root / ".claude" / "commands" / "reducer-repo.md"
            target.write_text("stale\n", encoding="utf-8")
            result = update_shortcuts(root, hosts=("claude-code",), scopes=("project",))
            self.assertEqual("re-rendered", result["results"][0]["action"])
            self.assertIn("repo-context run reducer-repo", target.read_text(encoding="utf-8"))

    def test_self_update_reports_commands_without_executing_them(self):
        with tempfile.TemporaryDirectory() as td:
            hint = self_update_hint(pathlib.Path(td))
            self.assertFalse(hint["executed"])
            self.assertIn("npx skills update", hint["commands"]["skill_package"])
            self.assertIn("pip install -U", hint["commands"]["python_cli"])


class MaintenanceCliTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> dict:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(argv)
        self.assertEqual(0, rc)
        return json.loads(out.getvalue())

    def test_remove_cli_defaults_to_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _seed_full_state(root)
            data = self._run(["remove", "--repo", td, "--target", "state"])
            self.assertTrue(data["dry_run"])
            self.assertTrue((root / ".repo-context" / "index.json").is_file())

    def test_update_cli_reports_every_section(self):
        with tempfile.TemporaryDirectory() as td:
            _seed(pathlib.Path(td))
            data = self._run(["update", "--repo", td, "--target", "all"])
            self.assertIn("index", data)
            self.assertIn("shortcuts", data)
            self.assertIn("self", data)
            self.assertFalse(data["self"]["executed"])

    def test_artifact_remove_deletes_one_record(self):
        with tempfile.TemporaryDirectory() as td:
            stored = ArtifactStore(pathlib.Path(td)).put({"k": "v"}, producer="tester")
            self._run(["artifact", "remove", stored["id"], "--repo", td])
            listed = self._run(["artifact", "list", "--repo", td])
            self.assertEqual([], listed["artifacts"])


if __name__ == "__main__":
    unittest.main()
