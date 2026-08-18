from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
from dataclasses import dataclass, asdict
from typing import Any, Iterable

from .config import load_config, is_trusted
from .provider_health import ProviderHealth

CAPABILITY_SCHEMA = "repo-context-capabilities/v1"

NATIVE_CAPABILITIES = {
    "repository.index", "repository.graph", "repository.symbols", "repository.imports",
    "repository.references", "repository.impact", "repository.search",
    "code.read-symbol", "code.structure", "git.changed", "git.diff",
    "context.budget", "context.dedup", "context.session", "context.delta",
    "context.lifecycle", "context.provenance", "context.handoff", "context.artifact",
    "context.fan-in", "context.contradiction", "context.synthesis-packet",
    "context.schema", "context.trust-boundary", "context.streaming", "context.tokenizer",
    "context.candidate-detection", "context.deterministic-verifier", "context.git-provenance",
    "context.filter-pipeline", "context.provenance-dedup", "context.cross-layer-dedup",
    "context.agreement-integrity", "context.model-packet", "context.model-context", "context.control-plane", "context.adaptive-reduction", "quality.filter-audit", "quality.token-economics", "quality.scenario-simulation",
    "quality.reducer-benchmark", "quality.final-answer-evaluation",
    "runtime.adapter", "runtime.execute", "runtime.cancellation", "runtime.backpressure", "runtime.telemetry",
    "runtime.sandbox", "runtime.checkpoint", "runtime.resume", "runtime.process-tree",
    "orchestration.parallel",
    "harness.trace", "harness.replay", "harness.tool-policy", "harness.fanout-policy",
    "harness.complexity", "harness.risk-routing", "harness.model-routing", "harness.retry-policy",
    "context.lane-budget", "quality.gate", "orchestration.scheduler", "orchestration.handoff",
    "knowledge.search", "knowledge.history",
}
CORE_CAPABILITIES = {
    "context.budget", "context.dedup", "context.session", "context.delta", "context.lifecycle",
    "context.provenance", "context.handoff", "context.artifact", "context.fan-in",
    "context.contradiction", "context.synthesis-packet", "context.schema", "context.trust-boundary",
    "context.streaming", "context.tokenizer", "context.candidate-detection",
    "context.deterministic-verifier", "context.git-provenance",
    "context.filter-pipeline", "context.provenance-dedup", "context.cross-layer-dedup",
    "context.agreement-integrity", "context.model-packet", "context.model-context", "context.control-plane", "context.adaptive-reduction", "quality.filter-audit", "quality.token-economics", "quality.scenario-simulation",
    "runtime.adapter", "runtime.execute", "runtime.cancellation", "runtime.backpressure", "runtime.telemetry",
    "runtime.sandbox", "runtime.checkpoint", "runtime.resume", "runtime.process-tree",
    "orchestration.parallel",
}
NATIVE_FALLBACK_CAPABILITIES = {
    "repository.index", "repository.graph", "repository.symbols", "repository.imports",
    "repository.references", "repository.impact", "repository.search", "code.read-symbol",
    "code.structure", "git.changed", "git.diff", "knowledge.search", "knowledge.history",
}
ADVISORY_CAPABILITIES = NATIVE_CAPABILITIES - CORE_CAPABILITIES - NATIVE_FALLBACK_CAPABILITIES
EXTERNAL_OPTIONAL_CAPABILITIES = {
    "knowledge.graph", "executor.code", "executor.autonomous",
    "model.cheap", "model.standard", "model.strong", "quality.grader",
}

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
    "context.fan-in": ("fan-in reducer", "fan in reducer", "aggregate worker outputs", "worker output reducer"),
    "context.contradiction": ("contradiction detection", "conflict detection", "worker disagreement"),
    "context.synthesis-packet": ("synthesis packet", "synthesis context", "final context pack"),
    "context.schema": ("json schema", "context contract", "worker output schema", "payload contract"),
    "context.trust-boundary": ("prompt injection", "untrusted context", "trust boundary", "instruction authority"),
    "context.streaming": ("ndjson", "streaming fan-in", "stream worker output", "jsonl"),
    "context.tokenizer": ("tokenizer", "token counter", "token budget", "tiktoken"),
    "context.candidate-detection": ("duplicate candidate", "semantic candidate", "candidate detector", "similar findings"),
    "context.deterministic-verifier": ("deterministic verifier", "safe merge", "merge verification"),
    "context.git-provenance": ("git provenance", "blob sha", "commit provenance", "content identity"),
    "context.filter-pipeline": ("filter pipeline", "content filtering", "dedup pipeline", "unified filter"),
    "context.provenance-dedup": ("provenance dedup", "duplicate provenance", "dedup support"),
    "context.cross-layer-dedup": ("cross layer dedup", "context overlap", "dominance filtering"),
    "context.agreement-integrity": ("agreement integrity", "unique worker agreement", "dedup votes"),
    "quality.filter-audit": ("filter audit", "dedup audit", "filter invariant", "merge invariant"),
    "context.model-packet": ("thin model packet", "model payload", "control plane sidecar"),
    "context.model-context": ("thin model context", "model context projection", "context sidecar"),
    "context.control-plane": ("control plane", "data plane", "model visible metadata"),
    "context.adaptive-reduction": ("adaptive reducer", "direct light full", "adaptive reduction"),
    "quality.token-economics": ("token economics", "token amplification", "net token savings"),
    "quality.scenario-simulation": ("scenario simulation", "reduction simulation", "strategy simulation"),
    "quality.reducer-benchmark": ("reducer benchmark", "correctness benchmark", "fan-in benchmark"),
    "runtime.adapter": ("runtime adapter", "agent runtime", "worker runtime"),
    "runtime.execute": ("execute agent plan", "spawn worker", "runtime execution"),
    "runtime.cancellation": ("cancel worker", "runtime cancellation", "terminate agent"),
    "runtime.backpressure": ("runtime backpressure", "bounded concurrency", "worker concurrency"),
    "runtime.telemetry": ("runtime telemetry", "cost telemetry", "latency telemetry", "usage telemetry"),
    "runtime.sandbox": ("sandbox runtime", "container runtime", "docker", "podman", "isolated worker"),
    "runtime.checkpoint": ("runtime checkpoint", "durable run", "persist run", "crash recovery"),
    "runtime.resume": ("resume run", "resume agent", "recover runtime", "continue run"),
    "runtime.process-tree": ("process tree", "child process cancellation", "kill process group"),
    "quality.final-answer-evaluation": ("final answer evaluation", "answer correctness gate", "required claims"),
}

KNOWN_CLI_CAPABILITIES = {"rg": {"repository.search"}, "git": {"git.changed", "git.diff"}}
SKILL_DIRS = (".claude/skills", ".agents/skills", ".cursor/skills", ".codex/skills")
GLOBAL_SKILL_DIRS = ("~/.claude/skills", "~/.agents/skills", "~/.cursor/skills", "~/.codex/skills")
REGISTERED_PROVIDER_DIRS = (".repo-context/providers.d", "~/.repo-context/providers.d")

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
        d=asdict(self); d["capabilities"]=sorted(set(self.capabilities)); return d


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


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"): return {}
    parts=text.split("---",2)
    if len(parts)<3:return {}
    out={}; current=None
    for raw in parts[1].splitlines():
        m=re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$",raw.rstrip())
        if m:
            current=m.group(1); out[current]=m.group(2).strip().strip('"\'')
        elif current and raw.startswith((" ","\t")): out[current]=(out.get(current,"")+" "+raw.strip()).strip()
    return out


def _guess_capabilities(description: str) -> list[str]:
    lower=description.lower(); return sorted({cap for cap,hints in CAPABILITY_HINTS.items() if any(h in lower for h in hints)})


def _load_manifest(path: pathlib.Path) -> dict[str, Any] | None:
    try:data=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError):return None
    return data if data.get("schema")==CAPABILITY_SCHEMA else None


def _manifest_from_dir(d: pathlib.Path) -> pathlib.Path | None:
    for n in ("capabilities.json",".capabilities.json","repo-context-capabilities.json"):
        p=d/n
        if p.is_file(): return p
    return None


def _provider_from_manifest(name: str, source_type: str, source: pathlib.Path, manifest: dict[str, Any]) -> Provider:
    caps=[]; commands={}
    for item in manifest.get("provides",[]):
        if isinstance(item,str): caps.append(item)
        elif isinstance(item,dict) and item.get("capability"):
            cap=str(item["capability"]); caps.append(cap)
            if item.get("command"): commands[cap]=item["command"]
    return Provider(id=f"{source_type}:{name}",name=name,source_type=source_type,source=str(source),capabilities=caps,compatible=True,trust="manifest-declared",executable=bool(commands),commands=commands or None,notes=["Declared by compatible capability manifest."])


def detect_skill_providers(root: pathlib.Path, required: set[str] | None=None) -> list[Provider]:
    out=[]; roots=[root/r for r in SKILL_DIRS]+[pathlib.Path(os.path.expanduser(r)) for r in GLOBAL_SKILL_DIRS]
    seen=set()
    for base in roots:
        try:children=list(base.iterdir())
        except OSError:continue
        for child in children:
            sf=child/"SKILL.md" if child.is_dir() else None
            if not sf or not sf.is_file():continue
            try:real=sf.resolve()
            except OSError:real=sf
            if real in seen:continue
            seen.add(real)
            try:text=sf.read_text(encoding="utf-8",errors="replace")[:12000]
            except OSError:continue
            fm=_frontmatter(text); name=fm.get("name") or child.name
            if name=="agent-repo-context-reducer":continue
            mp=_manifest_from_dir(child); manifest=_load_manifest(mp) if mp else None
            if manifest:
                p=_provider_from_manifest(name,"skill",child,manifest)
            else:
                caps=_guess_capabilities(fm.get("description",""))
                if not caps:continue
                p=Provider(id=f"skill:{name}",name=name,source_type="skill",source=str(child),capabilities=caps,compatible=False,trust="unknown",executable=False,confidence=.45,notes=["Potential overlap inferred from description only."])
            if not required or set(p.capabilities)&required:out.append(p)
    return out


def detect_registered_providers(root: pathlib.Path, required: set[str] | None=None) -> list[Provider]:
    out=[]
    for base in (root/REGISTERED_PROVIDER_DIRS[0],pathlib.Path(os.path.expanduser(REGISTERED_PROVIDER_DIRS[1]))):
        try:files=sorted(base.glob("*.json"))
        except OSError:continue
        for path in files:
            m=_load_manifest(path)
            if not m:continue
            meta=m.get("provider") or {}; name=str(meta.get("name") or path.stem); st=str(meta.get("type") or "registered")
            p=_provider_from_manifest(name,st,path,m); p.trust="registered-manifest"
            if not required or set(p.capabilities)&required:out.append(p)
    return out


def detect_cli_providers(required: set[str] | None=None) -> list[Provider]:
    out=[]
    for exe,caps in KNOWN_CLI_CAPABILITIES.items():
        if required and not caps&required:continue
        path=shutil.which(exe)
        if path:out.append(Provider(id=f"cli:{exe}",name=exe,source_type="cli",source=path,capabilities=sorted(caps),compatible=True,trust="known-adapter",executable=True))
    return out


def native_provider(required: set[str] | None=None) -> Provider:
    caps=NATIVE_CAPABILITIES if required is None else NATIVE_CAPABILITIES&required
    return Provider(id="native:repo-context",name="repo-context-native",source_type="native",source="bundled",capabilities=sorted(caps),compatible=True,trust="bundled",executable=True)


def detect_providers(repo_root: pathlib.Path | str, required: Iterable[str] | None=None, use_cache: bool=True) -> dict[str, Any]:
    root=pathlib.Path(repo_root).resolve(); req=set(required or [])
    providers=detect_skill_providers(root,req or None)+detect_registered_providers(root,req or None)+detect_cli_providers(req or None)
    native=native_provider(req or None)
    if native.capabilities:providers.append(native)
    return {"source":"scan","required":sorted(req),"providers":[p.json() for p in providers]}


def resolve_capability(repo_root: pathlib.Path | str, capability: str, allow_external_commands: bool=False) -> dict[str, Any]:
    root=pathlib.Path(repo_root).resolve(); detected=detect_providers(root,[capability],use_cache=False)
    candidates=[p for p in detected["providers"] if capability in p.get("capabilities",[])]
    native=next((p for p in candidates if p.get("source_type")=="native"),None)
    cfg=load_config(root); preferred=(cfg.get("preferred_providers") or {}).get(capability)
    external=[p for p in candidates if p.get("source_type") not in {"native","cli"}]
    cli=[p for p in candidates if p.get("source_type")=="cli"]
    selected=None; trusted=False
    eligible=[]
    for p in external:
        authorized=allow_external_commands or is_trusted(root,p.get("id",""))
        if p.get("compatible") and p.get("executable") and authorized:eligible.append(p)
    if preferred:
        selected=next((p for p in eligible if p.get("id")==preferred),None)
    if selected is None and eligible:
        selected=sorted(eligible,key=lambda p:(ProviderHealth(root).score_penalty(p.get("id","")),p.get("id","")))[0]
    if selected is None and cli:
        # Known CLIs are safe adapters for only specific capabilities.
        selected=cli[0]
    if selected is None: selected=native
    if selected and selected.get("source_type") not in {"native","cli"}: trusted=allow_external_commands or is_trusted(root,selected.get("id",""))
    potential=[p for p in external if p is not selected]
    return {"capability":capability,"selected":selected,"candidates":candidates,"trusted_selected":trusted,"potential_overlaps":potential,"source":detected["source"]}


def doctor(repo_root: pathlib.Path | str) -> dict[str, Any]:
    root=pathlib.Path(repo_root).resolve(); detected=detect_providers(root,use_cache=False); providers=detected["providers"]
    overlaps={}
    all_caps=sorted({c for p in providers for c in p.get("capabilities",[])})
    for cap in all_caps:
        ps=[p for p in providers if cap in p.get("capabilities",[])]
        non_native=[p for p in ps if p.get("source_type")!="native"]
        if non_native: overlaps[cap]=non_native
    return {"providers":providers,"overlaps":overlaps,"resolutions":{cap:resolve_capability(root,cap) for cap in sorted(NATIVE_CAPABILITIES)}}
