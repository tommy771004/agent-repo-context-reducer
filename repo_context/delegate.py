from __future__ import annotations

import json
import pathlib
import subprocess
import time
from typing import Any

from .capabilities import resolve_capability
from .external_context import canonicalize_external, deduplicate_blocks
from .provider_health import ProviderHealth
from .config import is_trusted

MAX_STDOUT_BYTES = 5_000_000


def _format_arg(value: str, *, root: pathlib.Path, task: str, capability: str) -> str:
    return value.replace("{repo}", str(root)).replace("{task}", task).replace("{query}", task).replace("{capability}", capability)


def delegate_capability(root: pathlib.Path | str, capability: str, task: str,
                        allow_external_commands: bool = False, timeout_seconds: int = 30) -> dict[str, Any]:
    root = pathlib.Path(root).resolve()
    resolution = resolve_capability(root, capability, allow_external_commands=allow_external_commands)
    selected = resolution["selected"]
    pid = selected.get("id", "")
    health = ProviderHealth(root)

    if selected.get("source_type") == "native":
        return {
            "delegated": False, "provider": selected, "resolution": resolution,
            "reason": "native-fallback-selected", "native_fallback_required": True,
        }

    if selected.get("source_type") == "cli":
        # Known CLI providers are invoked through capability-specific code elsewhere; generic delegate avoids guessing output semantics.
        return {
            "delegated": False, "provider": selected, "resolution": resolution,
            "reason": "known-cli-requires-capability-specific-adapter", "native_fallback_required": False,
        }

    command = (selected.get("commands") or {}).get(capability)
    if not (allow_external_commands or is_trusted(root, pid)):
        return {"delegated": False, "provider": selected, "resolution": resolution,
                "reason": "external-command-delegation-not-authorized", "native_fallback_required": True}
    if not isinstance(command, dict) or not isinstance(command.get("argv"), list) or not command["argv"]:
        return {"delegated": False, "provider": selected, "resolution": resolution,
                "reason": "adapter-must-declare-object-with-argv-array", "native_fallback_required": True}
    argv = [_format_arg(str(x), root=root, task=task, capability=capability) for x in command["argv"]]
    started = time.perf_counter()
    try:
        proc = subprocess.run(argv, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=max(1, timeout_seconds), check=False)
        latency = (time.perf_counter() - started) * 1000
        if len(proc.stdout) > MAX_STDOUT_BYTES:
            health.record(pid, False, latency)
            return {"delegated": False, "provider": selected, "resolution": resolution,
                    "reason": "provider-output-too-large", "stdout_bytes": len(proc.stdout), "native_fallback_required": True}
        if proc.returncode != 0:
            health.record(pid, False, latency)
            return {"delegated": False, "provider": selected, "resolution": resolution,
                    "reason": "provider-command-failed", "exit_code": proc.returncode,
                    "stderr": proc.stderr.decode("utf-8", errors="replace")[:2000], "native_fallback_required": True}
        try:
            payload = json.loads(proc.stdout.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            health.record(pid, False, latency)
            return {"delegated": False, "provider": selected, "resolution": resolution,
                    "reason": "provider-output-not-json", "error": str(exc), "native_fallback_required": True}
        blocks = deduplicate_blocks(canonicalize_external(selected.get("name", pid), payload))
        health.record(pid, True, latency)
        return {
            "delegated": True, "provider": selected, "resolution": resolution,
            "latency_ms": round(latency, 2), "blocks": blocks,
            "native_fallback_required": False,
            "execution": {"shell": False, "argv": argv, "timeout_seconds": timeout_seconds},
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        latency = (time.perf_counter() - started) * 1000
        health.record(pid, False, latency)
        return {"delegated": False, "provider": selected, "resolution": resolution,
                "reason": "provider-execution-error", "error": str(exc), "native_fallback_required": True}
