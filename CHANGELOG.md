# Changelog

## 2.2.0

- Added the Unified Filter & Dedup Engine across external context, context packs, handoffs, fan-in, synthesis, and runtime grading/finalization.
- Changed the production default for unstructured canonical grouping to `exact-claim`; `legacy-merge` remains explicit compatibility mode.
- Split occurrence, unique-worker agreement, independent source, and independent evidence accounting so repeated worker output cannot inflate consensus.
- Added string/bool/number assertion-side identity and ensured exact wording cannot override conflicting structured assertions.
- Added deterministic second-pass candidate merges plus whole-component identity/assertion validation and global ambiguous-bridge protection.
- Preserved unambiguous canonical/assertion fields when a candidate merge selects an identity-less higher-confidence representative.
- Added provenance-preserving external-context dedup scoped by exact content plus path/symbol identity.
- Added cross-layer structure dominance and session reference-only filtering for unchanged external context.
- Restricted handoff exact-list dedup to set-like top-level fields; nested sequences are preserved.
- Suppressed contradiction-side duplication between mandatory contradiction sections and ordinary synthesis findings while retaining reducer support metadata.
- Added bounded malformed/filtered diagnostics for both JSON batch and NDJSON streaming fan-in.
- Added raw-input-based filter savings accounting to avoid counting reducer-added trust metadata as token savings.
- Added bounded candidate generation for very large same-identity groups.
- Added Filter Summary, Dedup Support, and Filter Audit Draft 2020-12 contracts plus `repo-context filter-audit`.
- Added runtime filter invariant gates before synthesis and finalization.
- Expanded randomized batch/stream parity and adversarial transitive-merge validation.

## 2.1.0

- Added a native Podman/Docker container runtime adapter with deny-by-default network and repository write policy.
- Added read-only root/repository defaults, dropped capabilities, no-new-privileges, non-root user, PID/memory/CPU limits and bounded tmpfs.
- Disabled implicit container image pulls by default (`pull=never`); image pulling requires explicit runtime-network authorization.
- Split runtime external-execution, network and repository-write authorization into independent grants.
- Added process-group/session based subprocess cancellation so descendants are terminated on POSIX, with best-effort Windows process-tree cleanup.
- Added atomic durable runtime checkpoints under `.repo-context/runtime-runs/` and cumulative telemetry across resume operations.
- Added `runtime list`, `runtime inspect`, and `runtime resume`; successful nodes are retained and incomplete/failed nodes are re-executed.
- Added config/plan/budget-tokenizer fingerprint validation before resume.
- Added bounded Git repository drift identity based on HEAD plus changed path/index/working blob identities; drift blocks resume by default.
- Added Runtime State and Sandbox Policy Draft 2020-12 schemas and native runtime sandbox/checkpoint/resume/process-tree capabilities.
- Added v2.1 regression coverage for sandbox argv/policy, image-pull/network/write authorization, descendant cleanup, checkpoint resume, cumulative budgets/telemetry and Git drift protection.

## 2.0.0

- Added executable Runtime Adapter interface with host-registered in-process adapters and an explicitly authorized native subprocess adapter.
- Added canonical runtime invocation/result/telemetry contracts and `repo-context runtime status|execute`.
- Added real dependency-wave execution with bounded concurrency, fail-fast cancellation and wall/model/token backpressure.
- Added bounded worker retries with abstract model-tier escalation; concrete model mapping remains adapter/provider-owned.
- Added deterministic lane context slicing so each worker receives a bounded slice of the already-ranked context pack.
- Moved Fan-In onto the actual execution path: grader/integrator receive contradiction-preserving synthesis packets before they run.
- Made the grader quality gate executable: reject/uncertain outcomes stop finalization.
- Added per-attempt token/latency telemetry and provider-reported cost aggregation; no static price table or inferred USD cost.
- Added hard bounded subprocess stdout draining and direct-child termination on output overflow, timeout or cancellation.
- Added deterministic final-answer invariant evaluation and `repo-context evaluate-final`.
- Added `orchestration.parallel` as a native capability and persisted runtime telemetry under regenerable `.repo-context/telemetry/`.
- Added five Draft 2020-12 contracts for runtime config, invocation, result, telemetry and final-answer evaluation.
- Added end-to-end subprocess/runtime regression coverage for authorization, shell-free execution, parallel waves, retry escalation, cancellation, quality gating, backpressure and cost provenance.

## 1.7.0

- Added streaming NDJSON/JSONL fan-in through `FanInAccumulator`, `reduce_worker_stream()`, main CLI `fan-in`, and `repo-context-fan-in`.
- Streaming mode retains reducer groups plus bounded malformed diagnostics instead of the complete raw worker stream; exposes `peak_reducer_group_count` and streaming metadata.
- Added pluggable token estimators with dependency-free `native`, optional `tiktoken`, and explicit process-local host registration.
- Added tokenizer selection to context, handoff, fan-in and synthesis-packet budget paths.
- Added Git provenance for repository, file and symbol evidence: commit, HEAD/index/working-tree blob SHA, dirty state and content identity.
- Added `repo-context provenance` CLI and embedded Git provenance in selected context files/symbols.
- Added candidate detection with dependency-free lexical fallback and host-registerable semantic providers.
- Added deterministic candidate verification. Similarity can propose pairs but has no merge authority; exact identity/assertion verification decides whether a candidate is safe, conflicting or insufficient.
- Added `repo-context candidate-detect` and `repo-context tokenizer` CLI surfaces.
- Added Draft 2020-12 contracts for token estimates, Git provenance and candidate analysis.
- Added native capabilities for streaming, tokenizer selection, candidate detection, deterministic verification and Git provenance.
- Expanded regression coverage for streaming scale, bounded malformed diagnostics, custom tokenizers, Git dirty/clean identity and candidate/semantic-provider safety.

## 1.6.0

- Added formal Draft 2020-12 JSON contracts for finding, worker output, handoff, fan-in, contradiction, synthesis packet, trace events and benchmark cases.
- Added dependency-free built-in contract invariant validation and `repo-context schema` CLI.
- Added untrusted-content boundaries and prompt-injection-like signal classification for repository/provider/worker evidence.
- Integrated fan-in and synthesis-packet into the main `repo-context` CLI.
- Added deterministic worker-to-synthesis-packet correctness benchmark cases and `benchmark-e2e` CLI.
- Integrated schema, trust boundary and reducer benchmark capabilities into multi-agent planning.

## 1.5.0

- Added deterministic multi-worker Fan-In Reducer for the parallel-worker → final-agent boundary.
- Added exact/canonical grouping, agreement metadata, malformed diagnostics, and structured value/polarity contradiction surfacing.
- Corrected agreement semantics so contradictory asserted sides under the same fact identity are counted separately.
- Added bounded Synthesis Packet generation that preserves contradictions even when mandatory evidence exceeds the target budget.
- Upgraded `reduce_handoff()` with optional token-aware field selection.
- Added deterministic fan-in benchmark metrics and reducer-stage trace support.
- Added `repo-context-fan-in` CLI and native fan-in/contradiction/synthesis-packet capabilities.

## 1.4.0

- Made project-scope host shortcuts portable and added renderer drift tests.
- Consolidated persistent runtime state under `.repo-context/`.
- Expanded structural extraction for C/C++, shell, PowerShell and SQL.
- Added symbol reads, maintenance surfaces, cache generation guards and manifest consistency tests.

## 1.3.0

- Added deterministic risk/ambiguity routing, vendor-neutral model tiers, lane budgets, quality gate and bounded retry.

## 1.2.0

- Added task complexity routing, dependency-aware scheduling, handoff reducer, artifact store and local docs/ADR knowledge fallback.

## 1.1.0

- Added reducer intent facades and Claude Code/Codex host adapters.

## 0.2.0

- Added progressive Top-K output, task-aware ranking, dependency graph, changed/module/deps modes, cache and safety guards.

## 0.1.0

- Initial repository structural scanner and Agent Skill.
