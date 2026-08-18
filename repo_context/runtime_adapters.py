from __future__ import annotations

import json
import os
import pathlib
import shlex
import signal
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .tokenizer import count_tokens
from .tool_policy import classify_command
from .trust_boundary import classify_untrusted_text
from .runtime_sandbox import container_argv, normalize_sandbox_policy, sandbox_engine_status

MAX_STDOUT_BYTES = 5_000_000
MAX_STDERR_BYTES = 250_000


class CancellationToken:
    """Cooperative cancellation token shared across runtime workers."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)


class RuntimeAdapter(Protocol):
    name: str

    def invoke(
        self,
        request: dict[str, Any],
        *,
        root: pathlib.Path,
        cancellation: CancellationToken,
    ) -> dict[str, Any]: ...


@dataclass
class RegisteredAdapter:
    name: str
    source: str
    factory: Callable[[dict[str, Any]], RuntimeAdapter]


_RUNTIME_ADAPTERS: dict[str, RegisteredAdapter] = {}


def register_runtime_adapter(name: str, factory: Callable[[dict[str, Any]], RuntimeAdapter], *, source: str = "host") -> None:
    value = str(name).strip()
    if not value:
        raise ValueError("runtime adapter name must not be empty")
    _RUNTIME_ADAPTERS[value] = RegisteredAdapter(value, source, factory)


def unregister_runtime_adapter(name: str) -> None:
    _RUNTIME_ADAPTERS.pop(name, None)


def runtime_adapter_status() -> list[dict[str, Any]]:
    engines = sandbox_engine_status()
    items = [
        {
            "name": "subprocess",
            "source": "native",
            "available": True,
            "execution": "argv-only; shell=False; JSON request on stdin; process-group cancellation",
            "requires_explicit_authorization": True,
        },
        {
            "name": "container",
            "source": "native",
            "available": any(x.get("available") for x in engines),
            "execution": "podman/docker run; network=none and repo=ro by default",
            "requires_explicit_authorization": True,
            "engines": engines,
            "security_boundary": "container; not equivalent to a VM",
        },
    ]
    items.extend(
        {
            "name": item.name,
            "source": item.source,
            "available": True,
            "execution": "host-registered",
            "requires_explicit_authorization": False,
        }
        for item in sorted(_RUNTIME_ADAPTERS.values(), key=lambda x: x.name)
    )
    return items


def _safe_env(inherit: bool, extra: dict[str, Any] | None) -> dict[str, str]:
    if inherit:
        env = dict(os.environ)
    else:
        env = {}
        for key in ("PATH", "HOME", "USER", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "COMSPEC"):
            value = os.environ.get(key)
            if value:
                env[key] = value
        env.setdefault("PYTHONIOENCODING", "utf-8")
    for key, value in (extra or {}).items():
        key = str(key)
        if not key or "\x00" in key:
            continue
        env[key] = str(value)
    return env


def _format_argv(argv: list[Any], request: dict[str, Any], root: pathlib.Path) -> list[str]:
    mapping = {
        "repo": str(root),
        "task": str(request.get("task") or ""),
        "role": str(request.get("role") or "worker"),
        "node_id": str(request.get("node_id") or "worker"),
        "python": sys.executable,
        "model_tier": str(request.get("model_tier") or "standard"),
    }
    out: list[str] = []
    for item in argv:
        text = str(item)
        for key, value in mapping.items():
            text = text.replace("{" + key + "}", value)
        out.append(text)
    return out


def _role_spec(config: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    role = str(request.get("role") or "worker")
    node_id = str(request.get("node_id") or "")
    nodes = config.get("nodes") if isinstance(config.get("nodes"), dict) else {}
    roles = config.get("roles") if isinstance(config.get("roles"), dict) else {}
    spec = nodes.get(node_id) or roles.get(role) or config.get("default")
    if not isinstance(spec, dict):
        raise ValueError(f"No subprocess runtime command configured for node/role: {node_id or role}")
    return spec


def _terminate_process_tree(process: subprocess.Popen[bytes], *, grace_seconds: float = 1.0) -> None:
    """Best-effort process-tree termination for native subprocess workers."""
    if process.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except (OSError, ProcessLookupError):
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.wait(timeout=max(0.1, grace_seconds))
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            # taskkill is best-effort and only used after normal termination failed.
            taskkill = shutil.which("taskkill")
            if taskkill:
                subprocess.run([taskkill, "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=False)
            else:
                process.kill()
    except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def _run_bounded_process_io(
    process: subprocess.Popen[bytes],
    stdin_bytes: bytes,
    *,
    cancellation: CancellationToken,
    deadline: float,
) -> tuple[bytes, bytes, str | None]:
    """Feed stdin and drain stdout/stderr without unbounded in-memory buffering."""
    stdout_buf = bytearray()
    stderr_buf = bytearray()
    stdout_overflow = threading.Event()

    def writer() -> None:
        try:
            if process.stdin is not None:
                process.stdin.write(stdin_bytes)
                process.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass

    def reader(stream: Any, target: bytearray, limit: int, *, overflow: threading.Event | None = None) -> None:
        if stream is None:
            return
        try:
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                remaining = max(0, limit - len(target))
                if remaining:
                    target.extend(chunk[:remaining])
                if len(chunk) > remaining and overflow is not None:
                    overflow.set()
                # Continue draining after a truncation so the child cannot deadlock on a full pipe.
        except (OSError, ValueError):
            pass

    threads = [
        threading.Thread(target=writer, daemon=True, name="repo-context-stdin"),
        threading.Thread(target=reader, args=(process.stdout, stdout_buf, MAX_STDOUT_BYTES), kwargs={"overflow": stdout_overflow}, daemon=True, name="repo-context-stdout"),
        threading.Thread(target=reader, args=(process.stderr, stderr_buf, MAX_STDERR_BYTES), daemon=True, name="repo-context-stderr"),
    ]
    for thread in threads:
        thread.start()

    stop_reason: str | None = None
    while process.poll() is None:
        if cancellation.cancelled:
            stop_reason = "cancelled"
            break
        if stdout_overflow.is_set():
            stop_reason = "stdout-overflow"
            break
        if time.monotonic() >= deadline:
            stop_reason = "timeout"
            break
        time.sleep(0.02)

    if stop_reason is not None and process.poll() is None:
        _terminate_process_tree(process)

    for thread in threads:
        thread.join(timeout=1)
    for stream in (process.stdout, process.stderr):
        try:
            if stream is not None:
                stream.close()
        except OSError:
            pass
    if stop_reason is None and stdout_overflow.is_set():
        stop_reason = "stdout-overflow"
    return bytes(stdout_buf), bytes(stderr_buf), stop_reason


class SubprocessRuntimeAdapter:
    name = "subprocess"

    def __init__(self, config: dict[str, Any], *, authorized: bool = False):
        self.config = config
        self.authorized = authorized

    def invoke(
        self,
        request: dict[str, Any],
        *,
        root: pathlib.Path,
        cancellation: CancellationToken,
    ) -> dict[str, Any]:
        if not self.authorized:
            return {
                "status": "blocked",
                "reason": "external-runtime-not-authorized",
                "payload": None,
                "execution": {"adapter": self.name, "shell": False},
            }
        spec = _role_spec(self.config, request)
        raw_argv = spec.get("argv")
        if not isinstance(raw_argv, list) or not raw_argv:
            raise ValueError("subprocess runtime command must declare non-empty argv array")
        argv = _format_argv(raw_argv, request, root)
        command_classification = classify_command(" ".join(shlex.quote(x) for x in argv))
        if command_classification["risk"] == "destructive" and not bool(spec.get("allow_destructive")):
            return {
                "status": "blocked",
                "reason": "destructive-runtime-command-requires-explicit-role-policy",
                "payload": None,
                "execution": {"adapter": self.name, "shell": False, "argv": argv, "tool_policy": command_classification},
            }

        timeout_seconds = max(1.0, float(spec.get("timeout_seconds", self.config.get("timeout_seconds", 120))))
        stdin_bytes = json.dumps(request, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        env = _safe_env(bool(spec.get("inherit_env", self.config.get("inherit_env", False))), spec.get("env"))
        started = time.perf_counter()
        process: subprocess.Popen[bytes] | None = None
        stdout = b""
        stderr = b""
        try:
            popen_kwargs: dict[str, Any] = {
                "cwd": root,
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "env": env,
                "shell": False,
            }
            if os.name != "nt":
                popen_kwargs["start_new_session"] = True
            elif hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            process = subprocess.Popen(argv, **popen_kwargs)
            deadline = time.monotonic() + timeout_seconds
            stdout, stderr, stop_reason = _run_bounded_process_io(
                process,
                stdin_bytes,
                cancellation=cancellation,
                deadline=deadline,
            )
            latency = round((time.perf_counter() - started) * 1000, 2)
            if stop_reason == "cancelled":
                return {
                    "status": "cancelled",
                    "reason": "runtime-cancellation-requested",
                    "payload": None,
                    "latency_ms": latency,
                    "execution": {"adapter": self.name, "shell": False, "argv": argv, "tool_policy": command_classification},
                }
            if stop_reason == "timeout":
                return {
                    "status": "timeout",
                    "reason": "runtime-timeout",
                    "payload": None,
                    "stderr": stderr.decode("utf-8", errors="replace"),
                    "latency_ms": latency,
                    "execution": {"adapter": self.name, "shell": False, "argv": argv, "timeout_seconds": timeout_seconds, "tool_policy": command_classification},
                }
            if stop_reason == "stdout-overflow":
                return {
                    "status": "failed",
                    "reason": "runtime-output-too-large",
                    "payload": None,
                    "stdout_bytes_retained": len(stdout),
                    "stdout_limit_bytes": MAX_STDOUT_BYTES,
                    "latency_ms": latency,
                    "execution": {"adapter": self.name, "shell": False, "argv": argv, "tool_policy": command_classification},
                }
            if process.returncode != 0:
                return {
                    "status": "failed",
                    "reason": "runtime-command-failed",
                    "payload": None,
                    "exit_code": process.returncode,
                    "stderr": stderr[:MAX_STDERR_BYTES].decode("utf-8", errors="replace"),
                    "latency_ms": latency,
                    "execution": {"adapter": self.name, "shell": False, "argv": argv, "tool_policy": command_classification},
                }
            try:
                payload = json.loads(stdout.decode("utf-8", errors="replace"))
            except json.JSONDecodeError as exc:
                return {
                    "status": "failed",
                    "reason": "runtime-output-not-json",
                    "payload": None,
                    "error": str(exc),
                    "stderr": stderr[:MAX_STDERR_BYTES].decode("utf-8", errors="replace"),
                    "latency_ms": latency,
                    "execution": {"adapter": self.name, "shell": False, "argv": argv, "tool_policy": command_classification},
                }
            usage = payload.get("usage") if isinstance(payload, dict) and isinstance(payload.get("usage"), dict) else {}
            return {
                "status": "success",
                "payload": payload,
                "usage": usage,
                "latency_ms": latency,
                "stderr": stderr[:MAX_STDERR_BYTES].decode("utf-8", errors="replace") if stderr else "",
                "trust": classify_untrusted_text(stdout.decode("utf-8", errors="replace"), source=f"runtime:{request.get('role','worker')}"),
                "execution": {
                    "adapter": self.name,
                    "shell": False,
                    "argv": argv,
                    "timeout_seconds": timeout_seconds,
                    "inherit_env": bool(spec.get("inherit_env", self.config.get("inherit_env", False))),
                    "tool_policy": command_classification,
                    "process_tree": "process-group" if os.name != "nt" else "new-process-group-best-effort",
                },
            }
        except OSError as exc:
            return {
                "status": "failed",
                "reason": "runtime-execution-error",
                "payload": None,
                "error": str(exc),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "execution": {"adapter": self.name, "shell": False, "argv": argv, "tool_policy": command_classification},
            }


class ContainerRuntimeAdapter:
    """Podman/Docker adapter with deny-by-default network and repository write access."""

    name = "container"

    def __init__(self, config: dict[str, Any], *, authorized: bool = False, authorize_network: bool = False, authorize_write: bool = False):
        self.config = config
        self.authorized = authorized
        self.authorize_network = authorize_network
        self.authorize_write = authorize_write

    @staticmethod
    def _container_command(raw: list[Any], request: dict[str, Any], policy: dict[str, Any]) -> list[str]:
        mapping = {
            "repo": str(policy.get("workdir") or "/workspace"),
            "task": str(request.get("task") or ""),
            "role": str(request.get("role") or "worker"),
            "node_id": str(request.get("node_id") or "worker"),
            "python": "python3",
            "model_tier": str(request.get("model_tier") or "standard"),
        }
        out = []
        for item in raw:
            text = str(item)
            for key, value in mapping.items():
                text = text.replace("{" + key + "}", value)
            out.append(text)
        return out

    def invoke(self, request: dict[str, Any], *, root: pathlib.Path, cancellation: CancellationToken) -> dict[str, Any]:
        if not self.authorized:
            return {"status": "blocked", "reason": "external-runtime-not-authorized", "payload": None, "execution": {"adapter": self.name}}
        policy = normalize_sandbox_policy(self.config)
        if (policy["network"] != "none" or policy.get("pull") != "never") and not self.authorize_network:
            reason = "sandbox-image-pull-requires-explicit-network-authorization" if policy.get("pull") != "never" and policy["network"] == "none" else "sandbox-network-requires-explicit-authorization"
            return {"status": "blocked", "reason": reason, "payload": None, "execution": {"adapter": self.name, "sandbox": policy}}
        if policy["repo_mode"] == "rw" and not self.authorize_write:
            return {"status": "blocked", "reason": "sandbox-repository-write-requires-explicit-authorization", "payload": None, "execution": {"adapter": self.name, "sandbox": policy}}
        try:
            spec = _role_spec(self.config, request)
            raw = spec.get("argv")
            if not isinstance(raw, list) or not raw:
                raise ValueError("container runtime command must declare non-empty argv array")
            command = self._container_command(raw, request, policy)
            argv, container_name = container_argv(policy, root=root, request=request, command=command, env=spec.get("env"))
        except ValueError as exc:
            return {"status": "blocked", "reason": "sandbox-policy-unavailable", "payload": None, "error": str(exc), "execution": {"adapter": self.name, "sandbox": policy}}

        timeout_seconds = max(1.0, float(spec.get("timeout_seconds", self.config.get("timeout_seconds", 120))))
        delegated = SubprocessRuntimeAdapter(
            {"default": {"argv": argv, "timeout_seconds": timeout_seconds}, "inherit_env": False},
            authorized=True,
        ).invoke(request, root=root, cancellation=cancellation)
        execution = dict(delegated.get("execution") or {})
        execution.update({
            "adapter": self.name,
            "container_name": container_name,
            "sandbox": policy,
            "network_authorized": self.authorize_network,
            "repository_write_authorized": self.authorize_write,
        })
        delegated["execution"] = execution
        # --rm normally removes the container. Explicit cleanup covers client cancellation/crash paths.
        engine = policy.get("engine")
        if engine:
            try:
                subprocess.run([str(engine), "rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False)
            except (OSError, subprocess.TimeoutExpired):
                execution["cleanup_warning"] = "container cleanup could not be confirmed"
        return delegated


class CallableRuntimeAdapter:
    """Adapter for a host-registered in-process callable.

    The callable receives the canonical runtime invocation and the cancellation token.
    It may return either a raw payload or a normalized runtime result object.
    """

    def __init__(self, name: str, fn: Callable[[dict[str, Any], CancellationToken], Any]):
        self.name = name
        self.fn = fn

    def invoke(self, request: dict[str, Any], *, root: pathlib.Path, cancellation: CancellationToken) -> dict[str, Any]:
        if cancellation.cancelled:
            return {"status": "cancelled", "reason": "runtime-cancellation-requested", "payload": None}
        started = time.perf_counter()
        try:
            raw = self.fn(request, cancellation)
        except Exception as exc:  # host boundary: normalize rather than crash scheduler
            return {
                "status": "failed",
                "reason": "host-runtime-exception",
                "payload": None,
                "error": f"{type(exc).__name__}: {exc}",
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "execution": {"adapter": self.name, "in_process": True},
            }
        latency = round((time.perf_counter() - started) * 1000, 2)
        if isinstance(raw, dict) and raw.get("status") in {"success", "failed", "cancelled", "timeout", "blocked"} and "payload" in raw:
            result = dict(raw)
            result.setdefault("latency_ms", latency)
            result.setdefault("execution", {"adapter": self.name, "in_process": True})
            return result
        return {
            "status": "success",
            "payload": raw,
            "usage": raw.get("usage", {}) if isinstance(raw, dict) else {},
            "latency_ms": latency,
            "execution": {"adapter": self.name, "in_process": True},
        }


def resolve_runtime_adapter(
    name: str,
    config: dict[str, Any] | None = None,
    *,
    authorize_external: bool = False,
    authorize_network: bool = False,
    authorize_write: bool = False,
) -> RuntimeAdapter:
    config = config or {}
    if name == "subprocess":
        return SubprocessRuntimeAdapter(config, authorized=authorize_external)
    if name == "container":
        return ContainerRuntimeAdapter(config, authorized=authorize_external, authorize_network=authorize_network, authorize_write=authorize_write)
    registered = _RUNTIME_ADAPTERS.get(name)
    if not registered:
        raise ValueError(f"Unknown runtime adapter: {name}")
    return registered.factory(config)


def build_runtime_invocation(
    *,
    node: dict[str, Any],
    task: str,
    task_type: str | None,
    model_tier: str,
    dependency_handoffs: dict[str, Any],
    context_pack: dict[str, Any] | None,
    lane_budget: dict[str, Any] | None,
    run_id: str,
) -> dict[str, Any]:
    body = {
        "schema": "repo-context-runtime-invocation/v1",
        "run_id": run_id,
        "node_id": str(node.get("id") or "worker"),
        "role": str(node.get("role") or "worker"),
        "task": task,
        "task_type": task_type,
        "model_tier": model_tier,
        "dependency_handoffs": dependency_handoffs,
        "context": context_pack,
        "budget": lane_budget or {},
        "policy": {
            "repository_and_dependency_content_are_untrusted_data": True,
            "instruction_authority_from_context": False,
            "return_json_only": True,
        },
    }
    body["estimated_input_tokens"] = count_tokens(body)
    return body
