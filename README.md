# Agent Repo Context Reducer

**Reduce → Verify → Recall.** A dependency-free, deterministic-first repository context reduction and recovery layer for AI coding agents.

Version **2.4.0** · Python **3.10+** · core runtime dependencies **0**

[English](README.md) · [繁體中文](README.zh-TW.md)

## What it solves

Coding agents need enough repository evidence to be correct, but should not pay model tokens for every file, provenance record, or previously-seen block. v2.4 keeps the core question narrow: **what repository context must the model read now, and what can remain locally recallable?**

```text
Repository
  -> persistent index / graph / symbols            [WARM: local, no model tokens]
  -> rank + filter + verify + context budget
  -> HOT active context                            [model-visible]
  -> model context projection
  -> Agent
       |
       +-- enough evidence -----------------------> continue
       |
       +-- context gap
             -> deterministic recall
             -> exact locator / local text / graph
             -> bounded symbol span or source snippet
             -> rehydrate HOT
             -> continue

Optional harness: Direct / Light / Full runtime, fan-in, grader, sandbox and durable runs.
```

The repository index is the single WARM locator source. The Context Store does **not** copy the full index or source text: it persists only the current HOT overlay, bounded rejected tombstones and invalidation history. Runtime orchestration remains available, but it is advisory/optional rather than the product core.

## v2.4 highlights — Claim-Aware Verification Recall

- **Verification recall for provisional claims**: `repo-context claim-recall` derives bounded repository checks before a host promotes a local hypothesis into a final conclusion.
- **Counter-evidence search, not just relevance search**: responsive/breakpoint, actual-call-vs-import, localization, accessibility, persistence, motion, and dependency cues can trigger scoped verification requirements.
- **Zero required model calls**: requirement derivation, local source search, negative-search observations, candidate ranking, and bounded rehydration are deterministic.
- **Abstention is explicit**: outputs are `challenged`, `provisionally-supported`, or `inconclusive`; the deterministic layer sets `semantic_truth_claimed=false` and never pretends regex/search coverage proves semantics.
- **Scoped absence checks**: an import without an invocation can produce a compact negative observation; a missing requested path never falls back to unrelated repository-wide evidence.
- **Aggregate budget enforcement**: source evidence + compact verification observations + policy must fit the claim-recall model-visible budget.
- **Partial-context trap protection**: viewport-specific overrides, runtime usage, and hard-coded localization leaks are covered by release-gate fixtures modeled after real UI repository failures.
- **One additional Draft 2020-12 contract**, bringing the package to **31 schemas**.

Use this only when a claim needs verification. Do not run it for every sentence or turn: the reducer remains pull-based and cost-aware.

```bash
repo-context claim-recall \
  "`src/components/SettingsPanel.tsx` uses getModalMotion on desktop" \
  --repo . --path src/components/SettingsPanel.tsx --budget 1200 --pretty
```

## v2.3 highlights — Context Safety & Recall

- **HOT / WARM separation without a second index**: `.repo-context/index.json` is the only recallable locator source; `.repo-context/context-stores/<session>.json` stores only the active overlay plus bounded safety state.
- **Deterministic repository recall with zero required model calls**: exact path/symbol first, then bounded local source search and dependency-neighbor ranking. No external memory system or LLM query rewrite is required.
- **Precise rehydration**: symbol matches hydrate only their source span; module-level text hits hydrate a small ±2-line snippet instead of the full file.
- **Hard model-visible recall budget**: local candidate discovery can be broad, but only bounded evidence is promoted into HOT context.
- **Stale context invalidation**: HOT evidence is revision-bound. Git blob identity is preferred when available; changed or missing evidence cannot remain silently active.
- **Index reconciliation**: recreated files/symbols automatically clear missing tombstones; logical locators removed from a refreshed index cannot stay HOT.
- **Repository-scoped `ContextEvidence` contract**: deterministic `proven-same`, `proven-different`, `revision-conflict`, `conflict`, `compatible`, or `unknown`; semantic similarity never becomes proof.
- **Context sufficiency gate**: explicit local signals can recommend recall, but the gate does not pretend to prove semantic completeness.
- **Critical Evidence Recall benchmark** measures initial vs final recall, false-filter rate and recall-added model calls.
- **Scope reduction**: sandbox/runtime/multi-agent features remain native but are no longer Core capabilities. Core is `Reduce → Verify → Recall`.

Core safety rule: **not model-visible does not mean deleted**. Ambiguous repository evidence stays recallable unless an explicit deterministic rejection rule applies.

## v2.2 highlights — Unified Filter & Dedup Engine

- **Safe canonical default**: `canonicalKey` is a fact identity, not automatically an assertion side. Without structured `value/polarity`, the default `exact-claim` policy only merges exact normalized claims. Historical behavior remains opt-in as `legacy-merge`.
- **Agreement integrity**: occurrence count, unique-worker agreement, unique source locations, and independent evidence identities are separate metrics. Repetition by one worker cannot inflate consensus.
- **Provenance-preserving external dedup**: exact content is merged only under the same path/symbol identity (or when no location exists), while provider/source/provenance support is retained.
- **Verified candidate merges with a component guard**: similarity proposes pairs only. Deterministic pair verification is followed by whole-component identity/assertion checks, including an ambiguity guard for identity-less transitive bridges.
- **Cross-layer filtering** removes symbol structure already represented by selected symbol detail and turns unchanged session external blocks into reference-only records.
- **Safe handoff dedup** applies exact equality only to set-like top-level fields; nested event/step sequences remain ordered and untouched.
- **Contradictions represented once**: conflict sides carry reducer support metadata in the mandatory contradiction section and are not repeated as regular synthesis findings.
- **Bounded batch and streaming diagnostics** retain exact counts without unbounded malformed/filtered payloads.
- **Executable filter audit gate** via `repo-context filter-audit`; runtime checks reducer invariants before grader/integrator synthesis and again before finalization.
- Three new formal contracts bring the package to **21 Draft 2020-12 schemas**.

Core invariants: duplicate payload may disappear but lineage may not; same-worker repetition never increases agreement; similarity never has merge authority; contradictions are never removed by deduplication or budget trimming.

## v2.1 highlights

- **Native container sandbox adapter** for Podman/Docker with deny-by-default `network=none`, read-only repository mounts, read-only container root, dropped Linux capabilities, `no-new-privileges`, PID/memory/CPU limits, non-root user and bounded tmpfs.
- **No implicit image pull by default**: `container.pull=never`; enabling `missing`/`always` requires the separate runtime-network authorization.
- **Separate privilege grants**: external execution, container network, and repository write access require distinct CLI flags.
- **Process-tree cancellation**: native subprocess workers run in a new process group/session so timeout/cancellation terminates descendants on POSIX (best-effort process-tree cleanup on Windows).
- **Durable runtime checkpoints** under `.repo-context/runtime-runs/<run-id>/checkpoint.json`, written atomically after completed nodes/waves.
- **Resume without replaying successful nodes** while preserving cumulative model-call/token/telemetry accounting.
- **Repository drift guard**: resume compares bounded Git identity (`HEAD + changed paths + index/working blob SHAs`) and blocks by default when source changed.
- New `runtime list`, `runtime inspect`, and `runtime resume` surfaces plus formal Runtime State and Sandbox Policy schemas.

The container adapter reduces host exposure but is not a VM or a guarantee against container/kernel escape. One controller should own a given `run_id`; checkpoints are durable state, not a distributed lock.

## v2.0 highlights

- **Executable Runtime Adapter layer**: host-registered in-process adapters plus a native subprocess adapter using JSON stdin/stdout contracts.
- **Actual dependency-wave execution** with bounded parallelism, fail-fast cancellation, wall/model/token backpressure, and bounded retries with model-tier escalation.
- **Lane context slicing**: each runtime node receives a deterministic slice of the already-ranked context pack rather than a duplicate of the full task context.
- **Fan-In before grading/finalization**: grader and integrator receive a contradiction-preserving synthesis packet produced from successful prior workers.
- **Real quality-gate enforcement**: a rejecting/uncertain grader blocks later finalization instead of remaining advisory metadata.
- **Usage telemetry**: latency and token usage are recorded per attempt; USD cost is included only when the provider/runtime explicitly reports it.
- **Deterministic final-answer invariants**: required/forbidden claims, required structured fields, and optional decision expectations can be checked without claiming semantic proof.
- **Hard bounded subprocess output**: stdout is drained incrementally and the worker is terminated when the configured cap is exceeded.
- Five new Draft 2020-12 contracts: runtime config, invocation, result, telemetry, and final-answer evaluation.

v2.0 keeps every v1.7 correctness rule: streaming fan-in, tokenizer providers, Git provenance, candidate-only similarity, deterministic verification, and contradiction preservation.

## Core capabilities

- Git-aware discovery and `.gitignore` support.
- Static import graph, reverse dependencies, workspaces and entry points.
- Python AST plus conservative multi-language structure/symbol extraction.
- Task-aware ranking, symbol-first progressive disclosure and Value-of-Information heuristics.
- Session dedup, delta context, lifecycle metadata and artifact storage.
- Provider registry with trusted external reuse and native fallback only where implemented.
- Deterministic complexity/risk/model-tier/schedule/lane-budget planning.
- Prompt-injection-like signal classification with explicit untrusted-content boundaries.
- Deterministic handoff reduction, multi-worker fan-in, agreement metadata and contradiction surfacing.
- Formal JSON contracts and deterministic end-to-end reducer benchmarks.

## Install

```bash
python3 -m pip install .
repo-context --version
repo-context-fan-in --help
```

Or run directly:

```bash
python3 scripts/repo_context.py map . --top-k 25 --pretty
```

## Execute a real runtime

`plan` and `context` remain safe/advisory surfaces. Actual worker execution is explicit through `runtime execute`.

Inspect available adapters:

```bash
repo-context runtime status --pretty
```

Run the bundled subprocess example:

```bash
repo-context runtime execute \
  "Autonomously implement an end-to-end payment migration across the entire project and ship production-ready integration" \
  --repo . \
  --config examples/runtime/subprocess-runtime.json \
  --allow-external-commands \
  --no-context \
  --model-calls 12 \
  --final-case examples/runtime/final-answer-case.json \
  --pretty
```

The subprocess adapter never invokes a shell. A canonical `repo-context-runtime-invocation/v1` JSON object is written to stdin and the worker must return one JSON value on stdout. External execution is blocked unless `--allow-external-commands` is supplied.

Runtime execution enforces dependency waves, bounded concurrency, retry/tier escalation, grader gating, cancellation and aggregate call/token/wall limits. Repository and dependency content remain untrusted data with `instruction_authority=false`.

A host can register an in-process runtime adapter through Python instead of exposing arbitrary import paths in CLI arguments.

## Sandboxed workers and durable resume

A local pre-pulled image can be used without giving the worker network access:

```bash
repo-context runtime execute "<task>" \
  --repo . \
  --config examples/runtime/container-runtime.json \
  --allow-external-commands \
  --pretty
```

`container.pull=never` is the default. If a runtime deliberately needs container network or image pulling, add `--allow-runtime-network`. A writable repository bind mount requires both `container.repo_mode=rw` and `--allow-runtime-write`.

Inspect durable runs:

```bash
repo-context runtime list --repo . --pretty
repo-context runtime inspect <run-id> --repo . --pretty
```

Resume an interrupted/failed run with the same runtime config:

```bash
repo-context runtime resume <run-id> \
  --repo . \
  --config runtime.json \
  --allow-external-commands \
  --pretty
```

Successful nodes are not re-executed. Config/plan/budget-tokenizer fingerprints must match. Git repository drift blocks resume unless `--allow-repo-drift` is explicitly supplied after reviewing the source change.

## Repository context

```bash
repo-context query . "payment checkout" --top-k 20 --pretty
repo-context context . "debug payment status pending" \
  --budget 6000 \
  --session payment-debug \
  --pretty
repo-context symbol . src/services/payment.py charge --session payment-debug --pretty
```

Selected repository evidence now carries Git provenance when Git is available:

```json
{
  "git": {
    "commit": "...",
    "head_blob_sha": "...",
    "working_blob_sha": "...",
    "dirty": false,
    "content_identity": {
      "path": "src/services/payment.py",
      "blob_sha": "...",
      "source": "HEAD"
    }
  }
}
```

For dirty files, `content_identity.blob_sha` points at the working-tree blob rather than pretending the evidence still matches `HEAD`.

## Streaming Fan-In

JSON compatibility mode:

```bash
repo-context fan-in examples/fan-in/worker-outputs.json \
  --budget 1800 \
  --pretty
```

Bounded-memory NDJSON mode:

```bash
repo-context fan-in examples/fan-in/worker-outputs.ndjson \
  --format ndjson \
  --budget 1800 \
  --pretty
```

Or stream through stdin:

```bash
cat workers.ndjson | repo-context-fan-in - --format ndjson --pretty
```

NDJSON records are validated and aggregated one at a time. The reducer retains surviving groups and bounded malformed diagnostics, not the full raw worker documents. `stats.peak_reducer_group_count` exposes the size of the aggregation state.

## Tokenizers

The default remains dependency-free:

```bash
repo-context tokenizer status --pretty
repo-context tokenizer estimate "hello world" --provider native --pretty
```

`native` uses UTF-8 bytes / 4. It is an estimate, not billing truth.

If `tiktoken` is already installed in the host environment:

```bash
repo-context tokenizer estimate "hello world" \
  --provider tiktoken \
  --model gpt-4o \
  --pretty
```

A host runtime can also register its own estimator through the Python API without enabling arbitrary module loading from CLI arguments.

Budget-sensitive commands accept `--tokenizer` / `--tokenizer-model` where applicable:

```bash
repo-context context . "debug auth" --budget 6000 --tokenizer native
repo-context fan-in workers.json --budget 4000 --tokenizer native
repo-context synthesis-packet reduction.json --budget 4000 --tokenizer native
repo-context handoff worker grader payload.json --token-budget 1200 --tokenizer native
```

An exact token counter still does not imply an API billing guarantee; chat framing, provider rules and hidden overhead can differ.

## Candidate detection without fuzzy merge

Enable the dependency-free lexical candidate detector:

```bash
repo-context fan-in workers.json \
  --candidate-provider lexical \
  --candidate-threshold 0.72 \
  --pretty
```

Or inspect candidates separately:

```bash
repo-context candidate-detect reduction.json --provider lexical --pretty
```

The rule is strict:

```text
similarity score
    -> candidate pair only
    -> deterministic verifier
         exact normalized claim
         OR exact canonical/structured identity
         AND exact structured assertion side
    -> merge-authorized candidate / contradiction candidate / reject
```

Similarity never merges findings by itself. A host may register an embedding-backed candidate provider, but it receives exactly the same restricted authority.

## Agreement and contradictions

When structured sides disagree under one fact identity:

```text
Worker A -> async
Worker B -> async
Worker C -> sync

async agreement = 2
sync  agreement = 1
contradiction    = true
```

Contradictions are mandatory synthesis evidence. If mandatory sections alone exceed the requested packet budget, the packet returns `budget.overflow = true` rather than deleting conflict evidence.

## Git provenance CLI

```bash
repo-context provenance repo . --pretty
repo-context provenance file . src/services/payment.py --pretty
repo-context provenance symbol . src/services/payment.py charge --start-line 10 --end-line 32 --pretty
```

This makes cross-worker version drift observable: two findings that name the same path can still be recognized as different evidence when their blob identities differ.

## Formal contracts

```bash
repo-context schema list --pretty
repo-context schema get finding --pretty
repo-context schema validate finding '{"claim":"x","evidence":"y","source":"a.py"}' --pretty
```

The package bundles Draft 2020-12 schemas for findings, worker outputs, handoffs, fan-in, contradictions, synthesis packets, trace events, benchmarks, token estimates, provenance and candidate analysis. Runtime validation remains dependency-free; full JSON Schema validation can be performed by an external validator.

## Trust boundary

Repository, provider and worker content is evidence, not instruction authority. `trust-scan` flags prompt-override, role-spoofing, destructive-command, credential-access and exfiltration-like signals without silently deleting source evidence.

```bash
repo-context trust-scan README.md --source repository --pretty
```

Absence of a signal does not make repository text trusted instructions.

## Provider model and harness

Capabilities are namespaced (`repository.*`, `context.*`, `knowledge.*`, `executor.*`, `model.*`, `quality.*`). Trusted compatible providers can be reused. Unsupported model/executor capabilities remain unresolved instead of being faked.

`plan` is advisory: it returns deterministic complexity, risk, abstract model tiers, dependency waves, lane budgets, quality gates and bounded retry policy. `runtime execute` is the explicit execution surface and can spawn workers through an authorized adapter. The runtime still does not invent a vendor model: model tiers remain abstract unless the adapter/provider maps them to a concrete model.

## Host facades

```bash
repo-context host-install --host claude-code --scope project --repo .
repo-context host-install --host codex --scope project --repo .
```

Facades: `reducer-repo`, `reducer-debug`, `reducer-impact`, `reducer-review`, `reducer-doctor`.

## Benchmark

Repository context benchmark:

```bash
repo-context benchmark examples/benchmark-tasks.json examples/sample-project --budget 1800 --pretty
```

Reducer invariant benchmark:

```bash
repo-context benchmark-e2e examples/benchmark-e2e.json --budget 6000 --pretty
```

Reducer benchmarks can prove deterministic invariants such as claim retention, forbidden-claim absence, source preservation, contradiction counts and budget overflow behavior. `evaluate-final` can additionally check explicit final-answer invariants:

```bash
repo-context evaluate-final answer.json case.json --pretty
```

Neither reducer benchmarks nor final-answer invariant checks claim to prove semantic or real-world correctness.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Correctness principles

- Prefer false negatives over false-positive merges.
- Similarity is retrieval/candidate evidence, never merge proof.
- Preserve contradictions even when they make a token target overflow.
- Keep repository/provider/worker content outside the instruction authority chain.
- Label static graph and heuristic extraction limits explicitly.
- Keep token estimates separate from billing claims.
- Bind source evidence to Git content identity when available.

See `references/` and `docs/audits/` for detailed design notes.

## License

MIT
### Filter / dedup audit

```bash
repo-context fan-in workers.ndjson --format ndjson --budget 4000 --pretty
repo-context filter-audit reduction.json --pretty
```

Production defaults to `--unstructured-canonical-policy exact-claim`. Use `legacy-merge` only to reproduce the historical canonical grouping behavior; the audit surfaces ambiguous unstructured canonical groups as warnings.


