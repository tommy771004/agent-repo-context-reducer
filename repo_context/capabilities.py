from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import time
from dataclasses import dataclass, asdict
from typing import Any, Iterable

from .storage import prepare_state_dir, state_dir
from .provider_health import ProviderHealth
from .config import load_config, is_trusted

CAPABILITY_SCHEMA = "repo-context-capabilities/v1"

NATIVE_CAPABILITIES = {
    "repository.index",
    "repository.graph",
    "repository.symbols",
    "repository.imports",
    "repository.references",
    "repository.impact",
    "repository.search",
    "code.read-symbol",
    "code.structure",
    "git.changed",
    "git.diff",
    "context.budget",
    "context.dedup",
    "context.session",
    "context.delta",
    "context.lifecycle",
    "context.provenance",
    "harness.trace",
    "harness.replay",
    "harness.tool-policy",
    "harness.fanout-policy",
    "harness.complexity",
    "harness.risk-routing",
    "harness.model-routing",
    "harness.retry-policy",
    "context.lane-budget",
    "quality.gate",
    "orchestration.scheduler",
    "orchestration.handoff",
    "context.handoff",
    "context.artifact",
    "knowledge.search",
    "knowledge.history",
}
CORE_CAPABILITIES = {
    "context.budget", "context.dedup", "context.session", "context.delta",
    "context.lifecycle", "context.provenance", "context.handoff", "context.artifact",
}
NATIVE_FALLBACK_CAPABILITIES = {
    "repository.index", "repository.graph", "repository.symbols", "repository.imports",
    "repository.references", "repository.impact", "repository.search",
    "code.read-symbol", "code.structure", "git.changed", "git.diff",
    "knowledge.search", "knowledge.history",
}
ADVISORY_CAPABILITIES = NATIVE_CAPABILITIES - CORE_CAPABILITIES - NATIVE_FALLBACK_CAPABILITIES
EXTERNAL_OPTIONAL_CAPABILITIES = {
    "knowledge.graph", "executor.code", "executor.autonomous", "orchestration.parallel",
    "model.cheap", "model.standard", "model.strong", "quality.grader",
}


def native_capability_manifest(version: str) -> dict[str, Any]:
    return {
        "schema": CAPABILITY_SCHEMA,
        "provider": {"name": "agent-repo-context-reducer", "version": version},
        "provides": sorted(NATIVE_CAPABILITIES),
        "notes": {
            "core": sorted(CORE_CAPABILITIES),
            "fallback": sorted(NATIVE_FALLBACK_CAPABILITIES),
            "advisory": sorted(ADVISORY_CAPABILITIES),
            "external_optional": sorted(EXTERNAL_OPTIONAL_CAPABILITIES),
        },
    }


# These CLIs are only resolved for capabilities for which this project has a safe adapter.
KNOWN_CLI_CAPABILITIES = {
    "rg": {"repository.search"},
    "git": {"git.changed", "git.diff"},
}

SKILL_DIRS = (
    ".claude/skills",
    ".agents/skills",
    ".cursor/skills",
    ".codex/skills",
)
GLOBAL_SKILL_DIRS = (
    "~/.claude/skills",
    "~/.agents/skills",
    "~/.cursor/skills",
    "~/.codex/skills",
)
REGISTERED_PROVIDER_DIRS = (
    ".repo-context/providers.d",
    "~/.repo-context/providers.d",
)

CAPABILITY_HINTS: dict[str, tuple[str, ...]] = {
    "repository.graph": ("dependency graph", "code graph", "repository graph", "call graph"),
    "repository.symbols": ("symbol index", "symbols", "find symbol", "code symbols"),
    "repository.references": ("find references", "references", "callers"),
    "repository.search": ("code search", "repository search", "semantic search"),
    "repository.index": ("repository index", "code index", "index codebase"),
    "repository.impact": ("impact analysis", "affected files", "change impact"),
    "knowledge.search": ("knowledge search", "project memory", "documentation search", "rag", "graphrag"),
    "knowledge.graph": ("knowledge graph", "graphrag", "entity graph", "community graph"),
    "executor.code": ("coding agent", "code executor", "implement code", "terminal agent"),
    "executor.autonomous": ("autonomous developer", "autonomous coding", "engineering agent"),
    "orchestration.parallel": ("multi-agent", "multi agent", "parallel agents", "agent orchestration"),
    "orchestration.handoff": ("agent handoff", "handoff", "delegate agent"),
    "quality.grader": ("quality grader", "independent grader", "grade agent", "quality gate"),
    "model.cheap": ("cheap model", "fast model", "small model", "low cost model"),
    "model.standard": ("standard model", "coding model", "worker model"),
    "model.strong": ("strong model", "reasoning model", "frontier model", "high capability model"),
}


@dataclass
class Provider:
    id: str
    name: str
    source_type: str
    source: str
    capabilities: list[str]
    compatible: bool
    trust: str
    executable: bool = False
    commands: dict[str, Any] | None = None
    confidence: float = 1.0
    notes: list[str] | None = None

    def json(self) -> dict[str, Any]:
        data = asdict(self)
        data["capabilities"] = sorted(set(self.capabilities))
        return data


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    out: dict[str, str] = {}
    current: str | None = None
    for raw in parts[1].splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            current = m.group(1)
            value = m.group(2).strip().strip('"\'')
            out[current] = value
        elif current and line.startswith((" ", "\t")):
            out[current] = (out.get(current, "") + " " + line.strip()).strip()
    return out


def _guess_capabilities(description: str) -> list[str]:
    lower = description.lower()
    hits = []
    for capability, hints in CAPABILITY_HINTS.items():
        if any(h in lower for h in hints):
            hits.append(capability)
    return sorted(set(hits))


def _manifest_from_dir(skill_dir: pathlib.Path) -> pathlib.Path | None:
    for name in ("capabilities.json", ".capabilities.json", "repo-context-capabilities.json"):
        p = skill_dir / name
        if p.is_file():
            return p
    return None


def _load_manifest(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("schema") != CAPABILITY_SCHEMA:
        return None
    return data


def _provider_from_skill(skill_file: pathlib.Path) -> Provider | None:
    try:
        text = skill_file.read_text(encoding="utf-8", errors="replace")[:12000]
    except OSError:
        return None
    fm = _frontmatter(text)
    name = fm.get("name") or skill_file.parent.name
    desc = fm.get("description", "")
    if name == "agent-repo-context-reducer" or name == "agent-repo-context-reducer":
        return None
    manifest_path = _manifest_from_dir(skill_file.parent)
    manifest = _load_manifest(manifest_path) if manifest_path else None
    if manifest:
        provides = manifest.get("provides", [])
        caps: list[str] = []
        commands: dict[str, Any] = {}
        for item in provides:
            if isinstance(item, str):
                caps.append(item)
            elif isinstance(item, dict) and item.get("capability"):
                caps.append(str(item["capability"]))
                if item.get("command"):
                    commands[str(item["capability"])] = item["command"]
        return Provider(
            id=f"skill:{name}", name=name, source_type="skill", source=str(skill_file.parent),
            capabilities=caps, compatible=True, trust="manifest-declared", executable=bool(commands),
            commands=commands or None, confidence=1.0,
            notes=["Capabilities are declared by a compatible manifest; execution still requires trust/policy approval."],
        )
    guessed = _guess_capabilities(desc)
    if not guessed:
        return None
    return Provider(
        id=f"skill:{name}", name=name, source_type="skill", source=str(skill_file.parent),
        capabilities=guessed, compatible=False, trust="unknown", executable=False, confidence=0.45,
        notes=["Potential overlap inferred from SKILL.md description only; not safe for automatic delegation."],
    )


def _skill_roots(repo_root: pathlib.Path) -> Iterable[pathlib.Path]:
    for rel in SKILL_DIRS:
        yield repo_root / rel
    for raw in GLOBAL_SKILL_DIRS:
        yield pathlib.Path(os.path.expanduser(raw))


def detect_skill_providers(repo_root: pathlib.Path, required: set[str] | None = None) -> list[Provider]:
    providers: list[Provider] = []
    seen: set[pathlib.Path] = set()
    for base in _skill_roots(repo_root):
        try:
            children = list(base.iterdir())
        except OSError:
            continue
        for child in children:
            skill_file = child / "SKILL.md" if child.is_dir() else None
            if not skill_file or not skill_file.is_file():
                continue
            real = skill_file.resolve()
            if real in seen:
                continue
            seen.add(real)
            p = _provider_from_skill(skill_file)
            if p and (not required or set(p.capabilities) & required):
                providers.append(p)
    return providers


def detect_registered_providers(repo_root: pathlib.Path, required: set[str] | None = None) -> list[Provider]:
    out: list[Provider] = []
    dirs = [repo_root / REGISTERED_PROVIDER_DIRS[0], pathlib.Path(os.path.expanduser(REGISTERED_PROVIDER_DIRS[1]))]
    seen: set[pathlib.Path] = set()
    for base in dirs:
        try:
            files = sorted(base.glob("*.json"))
        except OSError:
            continue
        for path in files:
            try:
                real = path.resolve()
            except OSError:
                real = path
            if real in seen:
                continue
            seen.add(real)
            manifest = _load_manifest(path)
            if not manifest:
                continue
            meta = manifest.get("provider") or {}
            name = str(meta.get("name") or path.stem)
            source_type = str(meta.get("type") or "registered")
            caps: list[str] = []
            commands: dict[str, Any] = {}
            for item in manifest.get("provides", []):
                if isinstance(item, str):
                    caps.append(item)
                elif isinstance(item, dict) and item.get("capability"):
                    cap = str(item["capability"]); caps.append(cap)
                    if item.get("command"):
                        commands[cap] = item["command"]
            if required and not (set(caps) & required):
                continue
            out.append(Provider(
                id=f"{source_type}:{name}", name=name, source_type=source_type, source=str(path),
                capabilities=caps, compatible=True, trust="registered-manifest", executable=bool(commands),
                commands=commands or None, confidence=1.0,
                notes=["Registered provider manifest; machine invocation still requires an adapter and explicit policy approval."],
            ))
    return out


def detect_cli_providers(required: set[str] | None = None) -> list[Provider]:
    out: list[Provider] = []
    for exe, caps in KNOWN_CLI_CAPABILITIES.items():
        if required and not (caps & required):
            continue
        path = shutil.which(exe)
        if path:
            out.append(Provider(
                id=f"cli:{exe}", name=exe, source_type="cli", source=path,
                capabilities=sorted(caps), compatible=True, trust="known-adapter",
                executable=True, confidence=1.0,
            ))
    return out


def native_provider(required: set[str] | None = None) -> Provider:
    caps = NATIVE_CAPABILITIES if required is None else NATIVE_CAPABILITIES & required
    return Provider(
        id="native:repo-context", name="repo-context-native", source_type="native", source="bundled",
        capabilities=sorted(caps), compatible=True, trust="bundled", executable=True, confidence=1.0,
        notes=["Native implementation is fallback-first, not preferred over a trusted compatible external provider."],
    )


def _environment_signature(repo_root: pathlib.Path) -> str:
    h = hashlib.sha256()
    for base in _skill_roots(repo_root):
        try:
            st = base.stat()
            h.update(f"{base}:{st.st_mtime_ns}:{st.st_size}".encode())
        except OSError:
            continue
    for raw in REGISTERED_PROVIDER_DIRS:
        base = repo_root / raw if not raw.startswith("~") else pathlib.Path(os.path.expanduser(raw))
        try:
            st = base.stat(); h.update(f"{base}:{st.st_mtime_ns}:{st.st_size}".encode())
        except OSError:
            continue
    h.update(os.environ.get("PATH", "").encode())
    return h.hexdigest()


def _cache_path(repo_root: pathlib.Path) -> pathlib.Path:
    return state_dir(repo_root) / "providers.json"


def detect_providers(repo_root: pathlib.Path | str, required: Iterable[str] | None = None, use_cache: bool = True) -> dict[str, Any]:
    root = pathlib.Path(repo_root).resolve()
    req = set(required or [])
    signature = _environment_signature(root)
    cache = _cache_path(root)
    if use_cache:
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("environment_signature") == signature:
                providers = data.get("providers", [])
                if not req or any(set(p.get("capabilities", [])) & req for p in providers):
                    filtered = [p for p in providers if not req or set(p.get("capabilities", [])) & req]
                    return {"source": "cache", "required": sorted(req), "providers": filtered,
                            "environment_signature": signature, "detected_at": data.get("detected_at")}
        except (OSError, json.JSONDecodeError):
            pass
    providers = detect_skill_providers(root, req or None) + detect_registered_providers(root, req or None) + detect_cli_providers(req or None)
    # Native is always last and only advertises required capabilities when lazy detection is used.
    providers.append(native_provider(req or None))
    payload = {
        "environment_signature": signature,
        "detected_at": int(time.time()),
        "providers": [p.json() for p in providers],
    }
    prepare_state_dir(root)
    cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        cache.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except OSError:
        pass
    return {"source": "scan", "required": sorted(req), **payload}


def resolve_capability(repo_root: pathlib.Path | str, capability: str, allow_external_commands: bool = False) -> dict[str, Any]:
    detected = detect_providers(repo_root, required=[capability])
    candidates = [p for p in detected["providers"] if capability in p.get("capabilities", [])]
    resolved_root = pathlib.Path(repo_root).resolve()
    health = ProviderHealth(resolved_root)
    cfg = load_config(resolved_root)
    preferred = cfg.get("preferred_providers", {}).get(capability)
    # Explicit compatible external providers first, then known CLIs, native last. Historical health only breaks ties/penalizes repeatedly failing providers.
    def priority(p: dict[str, Any]) -> tuple[float, float, str]:
        preferred_bonus = -100.0 if preferred and p.get("id") == preferred else 0.0
        if p.get("source_type") == "native":
            return (preferred_bonus + 50 + health.score_penalty(p.get("id", "")), 0, p.get("id", ""))
        if not p.get("compatible"):
            return (preferred_bonus + 40 + health.score_penalty(p.get("id", "")), -float(p.get("confidence", 0)), p.get("id", ""))
        if p.get("source_type") == "skill" and p.get("executable") and not allow_external_commands:
            return (preferred_bonus + 25 + health.score_penalty(p.get("id", "")), -float(p.get("confidence", 0)), p.get("id", ""))
        if p.get("source_type") == "cli":
            return (preferred_bonus + 10 + health.score_penalty(p.get("id", "")), -float(p.get("confidence", 0)), p.get("id", ""))
        return (preferred_bonus + 5 + health.score_penalty(p.get("id", "")), -float(p.get("confidence", 0)), p.get("id", ""))
    candidates.sort(key=priority)
    usable = []
    overlaps = []
    for p in candidates:
        if not p.get("compatible"):
            overlaps.append(p)
            continue
        if p.get("source_type") not in {"native", "cli"}:
            if not p.get("executable"):
                overlaps.append({**p, "blocked_reason": "provider-has-no-machine-invokable-adapter"})
                continue
            if not (allow_external_commands or is_trusted(resolved_root, p.get("id", ""))):
                overlaps.append({**p, "blocked_reason": "external-command-delegation-not-authorized"})
                continue
        usable.append(p)
    native = native_provider({capability}).json() if capability in NATIVE_CAPABILITIES else None
    selected = usable[0] if usable else native
    return {
        "capability": capability,
        "selected": selected,
        "alternatives": usable[1:],
        "potential_overlaps": overlaps,
        "policy": "detect-reuse-delegate-native-fallback",
        "external_command_delegation": allow_external_commands,
        "trusted_selected": bool(selected) and is_trusted(resolved_root, selected.get("id", "")),
        "preferred_provider": preferred,
        "provider_health": {p.get("id", ""): health.summary(p.get("id", "")).get(p.get("id", "")) for p in candidates},
    }


def doctor(repo_root: pathlib.Path | str) -> dict[str, Any]:
    root = pathlib.Path(repo_root).resolve()
    detected = detect_providers(root, use_cache=False)
    by_cap: dict[str, list[dict[str, Any]]] = {}
    for p in detected["providers"]:
        for cap in p.get("capabilities", []):
            by_cap.setdefault(cap, []).append(p)
    overlaps = {
        cap: items for cap, items in by_cap.items()
        if len([p for p in items if p.get("source_type") != "native"]) > 0
    }
    return {
        "root": str(root),
        "providers": detected["providers"],
        "overlaps": overlaps,
        "recommendations": [
            "Use compatible manifest/known-adapter providers before native fallback.",
            "Do not auto-delegate to skills inferred only from description text.",
            "Keep repo-context as the context budget/dedup gateway even when graph/search comes from another provider.",
        ],
    }
