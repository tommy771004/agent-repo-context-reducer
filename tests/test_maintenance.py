from __future__ import annotations
import pathlib, tempfile, unittest
from repo_context.artifact_store import ArtifactStore
from repo_context.command_facade import FACADES
from repo_context.host_adapters import install_host_commands, host_status, uninstall_host_commands
from repo_context.indexer import build_persistent
from repo_context.maintenance import PRESERVED_STATE,REGENERABLE_STATE,remove_state,self_update_hint,state_inventory,update_shortcuts

def seed(root):
    (root/'main.py').write_text('def main(): return 1\n'); build_persistent(root,use_cache=True); ArtifactStore(root).put({'k':'v'},producer='tester'); (root/'.repo-context/providers.d').mkdir(parents=True,exist_ok=True); (root/'.repo-context/providers.d/mine.json').write_text('{}'); (root/'.repo-context/config.json').write_text('{}')
class MaintenanceTests(unittest.TestCase):
    def test_state_classes_do_not_overlap(self): self.assertFalse(set(REGENERABLE_STATE)&set(PRESERVED_STATE))
    def test_dry_run_default(self):
        with tempfile.TemporaryDirectory() as td:
            r=pathlib.Path(td); seed(r); x=remove_state(r); self.assertTrue(x['dry_run']); self.assertTrue((r/'.repo-context/index.json').is_file())
    def test_preserved_survive_default(self):
        with tempfile.TemporaryDirectory() as td:
            r=pathlib.Path(td); seed(r); remove_state(r,yes=True); self.assertFalse((r/'.repo-context/index.json').exists()); self.assertTrue((r/'.repo-context/config.json').exists()); self.assertTrue((r/'.repo-context/artifacts').exists())
    def test_all_removes_everything(self):
        with tempfile.TemporaryDirectory() as td:
            r=pathlib.Path(td); seed(r); remove_state(r,yes=True,include_preserved=True); self.assertFalse((r/'.repo-context').exists())
    def test_host_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            r=pathlib.Path(td); install_host_commands(r,'claude-code'); self.assertTrue(host_status(r,'claude-code')['all_installed']); x=uninstall_host_commands(r,'claude-code',yes=True); self.assertEqual(len(x['removed']),len(FACADES))
    def test_update_shortcuts(self):
        with tempfile.TemporaryDirectory() as td:
            r=pathlib.Path(td); install_host_commands(r,'claude-code'); target=r/'.claude/commands/reducer-repo.md'; target.write_text('stale'); x=update_shortcuts(r,hosts=('claude-code',),scopes=('project',)); self.assertEqual(x['results'][0]['action'],'re-rendered'); self.assertIn('repo-context run reducer-repo',target.read_text())
    def test_self_update_is_hint(self):
        with tempfile.TemporaryDirectory() as td: self.assertFalse(self_update_hint(pathlib.Path(td))['executed'])
if __name__=='__main__': unittest.main()
