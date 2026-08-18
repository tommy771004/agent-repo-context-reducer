from __future__ import annotations

import pathlib
import re
import shutil
from typing import Any


def _engine_path(value: str | None) -> str | None:
    raw = (value or "auto").strip()
    if raw == "auto":
        for name in ("podman", "docker"):
            found = shutil.which(name)
            if found:
                return found
        return None
    if pathlib.Path(raw).is_absolute():
        return raw if pathlib.Path(raw).is_file() else None
    return shutil.which(raw)


def sandbox_engine_status() -> list[dict[str, Any]]:
    out = []
    for name in ("podman", "docker"):
        path = shutil.which(name)
        out.append({"engine": name, "available": bool(path), "path": path})
    return out


def normalize_sandbox_policy(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("container") if isinstance(config.get("container"), dict) else {}
    network = str(raw.get("network") or "none")
    repo_mode = str(raw.get("repo_mode") or "ro")
    if repo_mode not in {"ro", "rw", "none"}:
        raise ValueError("container.repo_mode must be ro, rw, or none")
    if network not in {"none", "bridge", "host"} and not re.match(r"^[A-Za-z0-9_.:-]+$", network):
        raise ValueError("container.network contains unsupported characters")
    tmpfs = raw.get("tmpfs") if isinstance(raw.get("tmpfs"), list) else ["/tmp:rw,noexec,nosuid,size=64m"]
    pull = str(raw.get("pull") or "never")
    if pull not in {"never", "missing", "always"}:
        raise ValueError("container.pull must be never, missing, or always")
    policy = {
        "classification": "container-sandbox-policy",
        "engine_requested": str(raw.get("engine") or "auto"),
        "engine": _engine_path(str(raw.get("engine") or "auto")),
        "image": str(raw.get("image") or ""),
        "image_pinned": "@sha256:" in str(raw.get("image") or ""),
        "pull": str(raw.get("pull") or "never"),
        "network": network,
        "repo_mode": repo_mode,
        "workdir": str(raw.get("workdir") or "/workspace"),
        "read_only_root": bool(raw.get("read_only_root", True)),
        "drop_all_capabilities": bool(raw.get("drop_all_capabilities", True)),
        "no_new_privileges": bool(raw.get("no_new_privileges", True)),
        "pids_limit": max(16, int(raw.get("pids_limit", 128))),
        "memory": str(raw.get("memory") or "512m"),
        "cpus": max(0.1, float(raw.get("cpus", 1.0))),
        "user": str(raw.get("user") or "65534:65534"),
        "tmpfs": [str(x) for x in tmpfs[:8]],
        "security_note": "Container isolation reduces host exposure but is not equivalent to a VM security boundary.",
    }
    return policy


def container_argv(
    policy: dict[str, Any],
    *,
    root: pathlib.Path,
    request: dict[str, Any],
    command: list[str],
    env: dict[str, Any] | None = None,
) -> tuple[list[str], str]:
    engine = policy.get("engine")
    image = str(policy.get("image") or "")
    if not engine:
        raise ValueError("No supported container engine found; install podman/docker or set container.engine")
    if not image:
        raise ValueError("container.image is required")
    run_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(request.get("run_id") or "run"))[:40]
    node_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(request.get("node_id") or "worker"))[:32]
    attempt = int(request.get("attempt") or 1)
    name = f"repo-context-{run_id}-{node_id}-{attempt}"[:120]
    argv = [str(engine), "run", "--rm", "-i", "--name", name, "--pull", str(policy.get("pull") or "never")]
    argv += ["--label", f"repo-context.run_id={run_id}", "--label", f"repo-context.node_id={node_id}"]
    argv += ["--network", str(policy["network"])]
    if policy.get("read_only_root"):
        argv.append("--read-only")
    if policy.get("drop_all_capabilities"):
        argv += ["--cap-drop", "ALL"]
    if policy.get("no_new_privileges"):
        argv += ["--security-opt", "no-new-privileges"]
    argv += ["--pids-limit", str(policy["pids_limit"]), "--memory", str(policy["memory"]), "--cpus", str(policy["cpus"])]
    if policy.get("user"):
        argv += ["--user", str(policy["user"])]
    for entry in policy.get("tmpfs", []):
        argv += ["--tmpfs", str(entry)]
    repo_mode = str(policy["repo_mode"])
    if repo_mode != "none":
        suffix = ":ro" if repo_mode == "ro" else ":rw"
        argv += ["--volume", f"{root}:{policy['workdir']}{suffix}", "--workdir", str(policy["workdir"])]
    for key, value in (env or {}).items():
        key = str(key)
        if key and "\x00" not in key and "=" not in key:
            argv += ["--env", f"{key}={value}"]
    argv += [image, *[str(x) for x in command]]
    return argv, name
