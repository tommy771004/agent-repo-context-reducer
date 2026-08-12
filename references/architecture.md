# Architecture

## Primary pipeline

```text
User task
   |
   v
Task router
   |
   v
Required capabilities
   |
   v
Capability resolver
   |
   +--> trusted compatible Skill / registered MCP-plugin adapter
   +--> known safe CLI adapter
   `--> native fallback
            |
            v
      repository index / graph / symbols
            |
            v
Context gateway
   |
   +--> canonical identity
   +--> fingerprint
   +--> session dedup / delta
   +--> context lifecycle metadata
   +--> Value-of-Information prioritization
   +--> token budget
   +--> provenance
   |
   v
Minimal context pack
   |
   v
AI coding agent
```

## Harness layers

1. Task routing
2. Capability discovery/resolution
3. Provider trust/health
4. Native deterministic fallback
5. Read admission
6. Context planning/budget/lifecycle
7. Multi-agent backpressure policy
8. Tool-risk policy
9. Trace/replay
10. Benchmark/attribution

## Provider rule

Native graph/index/symbol implementations are fallbacks. They exist so the project remains useful in an empty environment; they are not intended to duplicate a compatible trusted provider.

Unknown Skills can be detected as potential overlap from metadata, but are not machine-compatible until an adapter/manifest is available.

## Native graph semantics

The bundled graph resolves local static imports and reverse imports. It is not a guaranteed runtime call graph. Dynamic dispatch, reflection, runtime dependency injection and generated runtime links may be absent.

## Context contract

The full index stays outside model context. The gateway emits only budgeted structural/symbol/external blocks with provenance and fingerprints. Session history can replace unchanged symbol bodies with small references.

## Enforcement boundary

The Python harness can control what **it** emits. A Skill alone cannot universally intercept every built-in Read/Grep/tool call of every agent. Hard enforcement requires host-runtime hooks/plugins/MCP/tool-gateway integration.
