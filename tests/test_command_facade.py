from __future__ import annotations
import contextlib, io, json, pathlib, tempfile, unittest
from repo_context.cli import main
from repo_context.command_facade import FACADES, get_facade
from repo_context.host_adapters import PORTABLE_PROJECT_RUNTIME, host_status, install_host_commands, render_claude_command, render_codex_skill
from repo_context.router import route_task

class CommandFacadeTests(unittest.TestCase):
    def test_all_short_commands_use_reducer_prefix(self): self.assertEqual(len(FACADES),5); self.assertTrue(all(n.startswith('reducer-') for n in FACADES))
    def test_debug_facade_forces_debug_route(self):
        r=route_task('explain project architecture',forced_type=get_facade('reducer-debug').intent); self.assertEqual(r['task_type'],'debug'); self.assertEqual(r['classification'],'explicit')
    def test_impact_facade_forces_change_impact(self): self.assertEqual(route_task('architecture',forced_type=get_facade('reducer-impact').intent)['task_type'],'change-impact')
    def test_claude_host_install_creates_five_slash_commands(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); result=install_host_commands(root,'claude-code',scope='project'); self.assertEqual(len(result['written']),5); self.assertTrue((root/'.claude/commands/reducer-debug.md').is_file()); self.assertTrue(host_status(root,'claude-code')['all_installed'])
    def test_codex_host_install_creates_named_skills(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); result=install_host_commands(root,'codex',scope='project'); self.assertEqual(len(result['written']),5); self.assertTrue((root/'.agents/skills/reducer-review/SKILL.md').is_file())
    def test_project_scope_shortcuts_use_portable_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            result=install_host_commands(pathlib.Path(td),'claude-code',scope='project'); self.assertEqual(result['runtime'],'repo-context'); self.assertTrue(result['portable'])
    def test_committed_host_snapshots_match_renderer(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        for spec in FACADES.values():
            self.assertEqual((root/'.claude/commands'/f'{spec.name}.md').read_text(),render_claude_command(spec,PORTABLE_PROJECT_RUNTIME))
            self.assertEqual((root/'adapters/codex'/spec.name/'SKILL.md').read_text(),render_codex_skill(spec,PORTABLE_PROJECT_RUNTIME))
    def test_cli_commands_lists_facades(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out): rc=main(['commands'])
        self.assertEqual(rc,0); names={x['name'] for x in json.loads(out.getvalue())['commands']}; self.assertIn('reducer-repo',names)
    def test_cli_debug_facade_forces_explicit_debug_workflow(self):
        with tempfile.TemporaryDirectory() as td:
            pathlib.Path(td,'main.py').write_text('def main():\n    return 1\n')
            out=io.StringIO()
            with contextlib.redirect_stdout(out): rc=main(['run','reducer-debug','explain project architecture','--repo',td,'--budget','900'])
            self.assertEqual(rc,0); self.assertEqual(json.loads(out.getvalue())['route']['task_type'],'debug')
    def test_reducer_doctor_facade_maps_to_doctor(self):
        with tempfile.TemporaryDirectory() as td:
            out=io.StringIO()
            with contextlib.redirect_stdout(out): rc=main(['run','reducer-doctor','--repo',td])
            self.assertEqual(rc,0); self.assertIn('providers',json.loads(out.getvalue()))
if __name__=='__main__': unittest.main()
