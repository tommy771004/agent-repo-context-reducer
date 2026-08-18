from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

from repo_context import __version__
from repo_context.capabilities import NATIVE_CAPABILITIES
from repo_context.cli import main
from repo_context.runtime_adapters import (
    CallableRuntimeAdapter,
    CancellationToken,
    ContainerRuntimeAdapter,
    SubprocessRuntimeAdapter,
    register_runtime_adapter,
    runtime_adapter_status,
    unregister_runtime_adapter,
)
from repo_context.runtime_engine import execute_runtime, load_runtime_config
from repo_context.runtime_sandbox import normalize_sandbox_policy
from repo_context.runtime_state import RuntimeCheckpointStore, list_runtime_runs
from repo_context.schema_registry import list_schemas, validate_contract


class V21ContractTests(unittest.TestCase):
    def test_version_is_v21_or_newer(self):
        self.assertGreaterEqual(tuple(int(x) for x in __version__.split(".")[:2]), (2, 1))

    def test_v21_capabilities_are_native(self):
        expected = {"runtime.sandbox", "runtime.checkpoint", "runtime.resume", "runtime.process-tree"}
        self.assertTrue(expected <= NATIVE_CAPABILITIES)

    def test_v21_schemas_are_registered(self):
        names = {x["name"] for x in list_schemas()}
        self.assertTrue({"runtime-state", "sandbox-policy"} <= names)

    def test_container_config_requires_image(self):
        with self.assertRaisesRegex(ValueError, "container.image"):
            load_runtime_config({"adapter": "container", "container": {}})


class SandboxAdapterTests(unittest.TestCase):
    @staticmethod
    def _fake_engine(root: pathlib.Path) -> pathlib.Path:
        engine = root / "fake-container-engine"
        engine.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "if len(sys.argv)>1 and sys.argv[1]=='rm': raise SystemExit(0)\n"
            "req=json.load(sys.stdin)\n"
            "role=req.get('role')\n"
            "out={'decision':'pass','score':0.99,'failures':[],'evidence':['ok']} if role=='grader' else {'summary':'sandbox ok'}\n"
            "out['usage']={'input_tokens':1,'output_tokens':1,'provider':'fake-container'}\n"
            "json.dump(out,sys.stdout)\n",
            encoding="utf-8",
        )
        engine.chmod(0o755)
        return engine

    def test_runtime_status_exposes_container_adapter(self):
        status = {x["name"]: x for x in runtime_adapter_status()}
        self.assertIn("container", status)
        self.assertEqual(status["container"]["security_boundary"], "container; not equivalent to a VM")

    def test_container_defaults_are_deny_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            engine = self._fake_engine(root)
            config = {
                "adapter": "container",
                "container": {"engine": str(engine), "image": "fake:image"},
                "default": {"argv": ["python3", "worker.py"], "timeout_seconds": 5},
            }
            result = execute_runtime(
                "Explain this function", root, runtime_config=config,
                context_tokens=1000, output_tokens=1000, model_calls=4,
                authorize_external=True,
            )
        self.assertTrue(result["success"])
        execution = result["nodes"]["work"]["execution"]
        self.assertEqual(execution["adapter"], "container")
        policy = execution["sandbox"]
        self.assertEqual(policy["network"], "none")
        self.assertEqual(policy["repo_mode"], "ro")
        self.assertTrue(policy["read_only_root"])
        self.assertTrue(policy["drop_all_capabilities"])
        self.assertTrue(policy["no_new_privileges"])
        argv = execution["argv"]
        self.assertIn("--read-only", argv)
        self.assertIn("--cap-drop", argv)
        self.assertIn("no-new-privileges", argv)
        self.assertIn("none", argv)
        self.assertTrue(any(str(root) in x and x.endswith(":ro") for x in argv))
        self.assertTrue(validate_contract("sandbox-policy", policy)["valid"])

    def test_container_network_requires_separate_authorization(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); engine = self._fake_engine(root)
            config = {"adapter":"container","container":{"engine":str(engine),"image":"x","network":"bridge"},"default":{"argv":["worker"]}}
            adapter = ContainerRuntimeAdapter(config, authorized=True, authorize_network=False)
            result = adapter.invoke({"run_id":"r","node_id":"w","role":"worker","task":"x"}, root=root, cancellation=CancellationToken())
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "sandbox-network-requires-explicit-authorization")

    def test_container_image_pull_requires_network_authorization(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); engine = self._fake_engine(root)
            config = {"adapter":"container","container":{"engine":str(engine),"image":"x","pull":"missing"},"default":{"argv":["worker"]}}
            adapter = ContainerRuntimeAdapter(config, authorized=True, authorize_network=False)
            result = adapter.invoke({"run_id":"r","node_id":"w","role":"worker","task":"x"}, root=root, cancellation=CancellationToken())
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "sandbox-image-pull-requires-explicit-network-authorization")

    def test_container_repo_write_requires_separate_authorization(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); engine = self._fake_engine(root)
            config = {"adapter":"container","container":{"engine":str(engine),"image":"x","repo_mode":"rw"},"default":{"argv":["worker"]}}
            adapter = ContainerRuntimeAdapter(config, authorized=True, authorize_write=False)
            result = adapter.invoke({"run_id":"r","node_id":"w","role":"worker","task":"x"}, root=root, cancellation=CancellationToken())
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "sandbox-repository-write-requires-explicit-authorization")

    @unittest.skipIf(os.name == "nt", "POSIX process-group semantics required")
    def test_subprocess_timeout_terminates_descendant_process_group(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            marker = root / "child-survived.txt"
            child_code = f"import time; time.sleep(1.5); open({str(marker)!r},'w').write('survived')"
            script = root / "parent.py"
            script.write_text(
                "import json,subprocess,sys,time\n"
                "json.load(sys.stdin)\n"
                f"subprocess.Popen([sys.executable,'-c',{child_code!r}])\n"
                "time.sleep(5)\n",
                encoding="utf-8",
            )
            adapter = SubprocessRuntimeAdapter({"default":{"argv":[sys.executable,str(script)],"timeout_seconds":1}}, authorized=True)
            result = adapter.invoke({"run_id":"r","node_id":"w","role":"worker","task":"x"}, root=root, cancellation=CancellationToken())
            time.sleep(1.0)
            self.assertEqual(result["status"], "timeout")
            self.assertFalse(marker.exists(), "child process must not survive process-group cancellation")


class DurableRuntimeTests(unittest.TestCase):
    def tearDown(self):
        unregister_runtime_adapter("resume-runtime")
        unregister_runtime_adapter("drift-runtime")

    @staticmethod
    def _payload(request):
        usage = {"input_tokens":1,"output_tokens":1,"provider":"resume-test"}
        if request["role"] == "grader":
            return {"decision":"pass","score":0.99,"failures":[],"evidence":["ok"],"usage":usage}
        if request["role"] == "integrator":
            return {"answer":"done","usage":usage}
        return {"summary":f"{request['node_id']} done","findings":[{"claim":f"{request['node_id']} done","evidence":"ok","source":f"runtime:{request['node_id']}"}],"usage":usage}

    def test_checkpoint_resume_skips_successful_nodes_and_continues_budget_counters(self):
        calls: dict[str,int] = {}
        phase = {"fail": True}
        def fn(request, cancellation):
            node = request["node_id"]
            calls[node] = calls.get(node, 0) + 1
            if node == "implement" and phase["fail"]:
                return {"status":"failed","reason":"simulated-crash","payload":None}
            return self._payload(request)
        register_runtime_adapter("resume-runtime", lambda config: CallableRuntimeAdapter("resume-runtime", fn))
        task = "Autonomously implement an end-to-end migration across the entire project and ship production-ready integration"
        config = {"adapter":"resume-runtime","max_attempts":1}
        with tempfile.TemporaryDirectory() as td:
            first = execute_runtime(task, td, runtime_config=config, adapter_name="resume-runtime", context_tokens=5000, output_tokens=5000, model_calls=20, concurrency=2, run_id="durable-1")
            self.assertFalse(first["success"])
            state = RuntimeCheckpointStore(td, "durable-1").load()
            self.assertTrue(validate_contract("runtime-state", state)["valid"])
            first_calls = dict(calls)
            phase["fail"] = False
            second = execute_runtime(task, td, runtime_config=config, adapter_name="resume-runtime", context_tokens=5000, output_tokens=5000, model_calls=20, concurrency=2, run_id="durable-1", resume=True)
            summary = RuntimeCheckpointStore(td, "durable-1").summary()
        self.assertTrue(second["success"])
        self.assertTrue(second["resumed"])
        self.assertEqual(second["resume_count"], 1)
        self.assertEqual(calls.get("plan"), first_calls.get("plan"), "successful plan node must not rerun")
        self.assertEqual(calls.get("research-a"), first_calls.get("research-a"), "successful research node must not rerun")
        self.assertGreater(calls.get("implement", 0), first_calls.get("implement", 0))
        self.assertGreater(second["backpressure"]["model_calls_used"], first["backpressure"]["model_calls_used"])
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(second["telemetry"]["attempts"], second["backpressure"]["model_calls_used"])

    @unittest.skipUnless(subprocess.run(["git","--version"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode == 0, "git required")
    def test_resume_blocks_repository_drift_unless_explicitly_allowed(self):
        phase={"fail":True}
        def fn(request,cancellation):
            if request["role"] == "grader": return self._payload(request)
            if phase["fail"]: return {"status":"failed","reason":"stop","payload":None}
            return self._payload(request)
        register_runtime_adapter("drift-runtime", lambda config: CallableRuntimeAdapter("drift-runtime", fn))
        config={"adapter":"drift-runtime","max_attempts":1}
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)
            subprocess.run(["git","init","-q",str(root)],check=True)
            subprocess.run(["git","-C",str(root),"config","user.email","test@example.com"],check=True)
            subprocess.run(["git","-C",str(root),"config","user.name","Test"],check=True)
            (root/".gitignore").write_text(".repo-context/\n",encoding="utf-8")
            (root/"main.py").write_text("x=1\n",encoding="utf-8")
            subprocess.run(["git","-C",str(root),"add","."],check=True)
            subprocess.run(["git","-C",str(root),"commit","-qm","init"],check=True)
            first=execute_runtime("Explain this function",root,runtime_config=config,adapter_name="drift-runtime",context_tokens=1000,output_tokens=1000,model_calls=10,run_id="drift-1")
            self.assertFalse(first["success"])
            (root/"main.py").write_text("x=2\n",encoding="utf-8")
            phase["fail"]=False
            with self.assertRaisesRegex(ValueError,"repository drift"):
                execute_runtime("Explain this function",root,runtime_config=config,adapter_name="drift-runtime",context_tokens=1000,output_tokens=1000,model_calls=10,run_id="drift-1",resume=True)
            resumed=execute_runtime("Explain this function",root,runtime_config=config,adapter_name="drift-runtime",context_tokens=1000,output_tokens=1000,model_calls=10,run_id="drift-1",resume=True,allow_repo_drift=True)
        self.assertTrue(resumed["success"])
        self.assertTrue(resumed["policy"]["repository_drift_allowed"])

    def test_runtime_list_and_inspect_cli(self):
        register_runtime_adapter("resume-runtime", lambda config: CallableRuntimeAdapter("resume-runtime", lambda req,c: self._payload(req)))
        with tempfile.TemporaryDirectory() as td:
            result=execute_runtime("Explain this function",td,runtime_config={"adapter":"resume-runtime","max_attempts":1},adapter_name="resume-runtime",context_tokens=1000,output_tokens=1000,model_calls=5,run_id="cli-run")
            self.assertTrue(result["success"])
            out=io.StringIO()
            with contextlib.redirect_stdout(out): rc=main(["runtime","inspect","cli-run","--repo",td])
            self.assertEqual(rc,0); inspected=json.loads(out.getvalue()); self.assertEqual(inspected["run_id"],"cli-run")
            out=io.StringIO()
            with contextlib.redirect_stdout(out): rc=main(["runtime","list","--repo",td])
            self.assertEqual(rc,0); listed=json.loads(out.getvalue()); self.assertTrue(any(x["run_id"]=="cli-run" for x in listed["runs"]))
            self.assertTrue(list_runtime_runs(td))


if __name__ == "__main__":
    unittest.main()
