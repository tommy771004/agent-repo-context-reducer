from __future__ import annotations
import pathlib, tempfile, unittest
from repo_context.cache import CACHE_VERSION, SummaryCache
from repo_context.parsers import summarize_source
from repo_context.scanner import build_index
from repo_context.symbols import extract_symbol_index, read_symbol
C_SOURCE='#include <stdio.h>\n#include "local.h"\nint add(int a, int b) { return a + b; }\nstatic void run(void) { printf("x"); }\n'
SHELL_SOURCE='source ./lib.sh\ndeploy() {\n echo hi\n}\nfunction rollback {\n echo no\n}\n'
PS_SOURCE='Import-Module Az\n. .\\helper.ps1\nfunction Get-Order {\n param($id)\n return $id\n}\n'
SQL_SOURCE='CREATE TABLE orders (id INT PRIMARY KEY);\ncreate view paid AS\nSELECT * FROM orders;\nCREATE OR REPLACE PROCEDURE settle_all()\nBEGIN\n UPDATE orders SET id = 1;\nEND;\n'
class LanguageExtractionTests(unittest.TestCase):
    def test_c_extracts(self):
        s=summarize_source('main.c',C_SOURCE); self.assertIn('./local.h',s['imports']); self.assertIn('stdio.h',s['imports']); self.assertIn('add(int a, int b)',s['functions'])
    def test_shell_extracts(self):
        s=summarize_source('deploy.sh',SHELL_SOURCE); self.assertIn('./lib.sh',s['imports']); self.assertEqual({'deploy','rollback'},{x.split('(')[0] for x in s['functions']})
    def test_powershell_extracts(self):
        s=summarize_source('run.ps1',PS_SOURCE); self.assertIn('Az',s['imports']); self.assertIn('./helper.ps1',s['imports']); self.assertIn('Get-Order',s['symbols'])
    def test_sql_extracts(self):
        s=summarize_source('schema.sql',SQL_SOURCE); self.assertIn('orders',s['types']); self.assertIn('paid',s['types']); self.assertIn('settle_all()',s['functions'])
    def test_symbol_reading_new_languages(self):
        for name,source,sym,expected in [('main.c',C_SOURCE,'add','int add'),('deploy.sh',SHELL_SOURCE,'deploy','echo hi'),('run.ps1',PS_SOURCE,'Get-Order','param($id)'),('schema.sql',SQL_SOURCE,'orders','CREATE TABLE orders')]:
            with tempfile.TemporaryDirectory() as td:
                root=pathlib.Path(td); (root/name).write_text(source); self.assertIn(expected,read_symbol(root,name,sym)['content'])
    def test_graph_edges(self):
        with tempfile.TemporaryDirectory() as td:
            r=pathlib.Path(td); (r/'local.h').write_text('int add(int a,int b);\n'); (r/'main.c').write_text(C_SOURCE); (r/'lib.sh').write_text('echo lib\n'); (r/'deploy.sh').write_text(SHELL_SOURCE); (r/'helper.ps1').write_text('Write-Host x\n'); (r/'run.ps1').write_text(PS_SOURCE)
            idx=build_index(r,use_cache=False); self.assertIn('local.h',idx['graph']['edges'].get('main.c',[])); self.assertIn('lib.sh',idx['graph']['edges'].get('deploy.sh',[])); self.assertIn('helper.ps1',idx['graph']['edges'].get('run.ps1',[]))
    def test_cache_version(self):
        with tempfile.TemporaryDirectory() as td:
            r=pathlib.Path(td); d=r/'.repo-context/cache'; d.mkdir(parents=True); (d/'summaries-v3.json').write_text('{"version":3,"items":{}}'); c=SummaryCache(r); self.assertEqual(CACHE_VERSION,c.data['version']); c.put('x','k',{}); c.save(); self.assertFalse((d/'summaries-v3.json').exists())
if __name__=='__main__': unittest.main()
