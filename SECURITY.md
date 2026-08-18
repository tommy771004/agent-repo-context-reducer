# Security Policy

## Trust model

Agent Repo Context Reducer scans local repositories and emits structural metadata. The repository scanner is designed to reduce accidental ingestion of secrets and unrelated filesystem content, but it is not a secret scanner; execution isolation is a separate optional runtime boundary.

## Default protections

The scanner skips:

- `.env` / `.env.*`
- paths containing common `secret` or `credential` names
- private-key-like extensions and SSH private key names
- symlinks
- binary files
- files over the configured size limit
- generated/minified code by default
- common vendor/build/cache directories

`inspect` refuses secret-like paths.

## What is not guaranteed

Secrets can exist in ordinary source files with ordinary names. The tool does not inspect values and cannot guarantee that output contains no sensitive identifiers or literals exposed through function/type/route signatures.

Review repository trust boundaries before running tools in sensitive environments.

## Reporting

Please report security-sensitive issues privately through GitHub's security advisory mechanism when available rather than opening a public issue with exploit or secret material.

## v2.0+ runtime execution boundary

`repo-context runtime execute` can execute external worker programs. This is intentionally separate from repository scanning and planning.

Default runtime protections:

- subprocess execution is blocked unless the caller explicitly supplies `--allow-external-commands`;
- argv is executed directly with `shell=False`;
- canonical runtime input is passed as JSON on stdin rather than interpolated into a shell command;
- the subprocess environment is minimized by default; `inherit_env=true` is an explicit configuration decision and may expose secrets already present in the parent environment;
- stdout/stderr are drained with bounded buffers and oversized stdout terminates the worker;
- timeouts and cancellation terminate the subprocess process group/session on POSIX; Windows process-tree cleanup is best-effort;
- repository, dependency-handoff and worker text remain untrusted evidence and do not gain instruction authority.

The subprocess adapter is **not a sandbox**. A worker program can still access the filesystem and network according to the operating-system permissions of the parent process and can perform side effects before cancellation.

## v2.1 container sandbox boundary

The optional `container` runtime adapter uses Podman/Docker and defaults to no container network, no implicit image pull, a read-only repository bind mount, read-only root filesystem, dropped Linux capabilities, `no-new-privileges`, non-root user and bounded PID/memory/CPU/tmpfs resources. Starting the engine still requires explicit external-execution authorization. Container network/image pull and repository write are separate explicit grants.

Important limits:

- a container is not a VM and does not eliminate kernel/container-runtime escape risk;
- the host container engine/daemon remains part of the trusted computing base;
- allowing `pull=missing|always` lets the engine use host networking to fetch images and therefore requires runtime-network authorization;
- `repo_mode=rw` gives the container direct write access to the host repository and requires separate write authorization;
- do not mount Docker/Podman sockets, credential directories, SSH agents, cloud metadata proxies or secret files into untrusted workers;
- image tags are mutable; pin image digests when reproducibility/supply-chain integrity matters.

Durable runtime checkpoints may contain bounded worker payloads, reduced handoffs and evidence. `.repo-context/` should be treated as local runtime data and is gitignored by default. Resume blocks Git source drift by default, but checkpoints are not a distributed lock: use one controller per `run_id`.

Provider-reported token/cost metadata is treated as telemetry, not as proof of billing correctness. The runtime never derives USD cost from an embedded price table.

## v2.2 filter/dedup correctness boundary

- Similarity and embedding scores are candidate signals only and never authorize merges.
- Default unstructured canonical policy is `exact-claim`; `legacy-merge` is explicit compatibility mode and may surface ambiguity warnings.
- Pair-wise verified merges are additionally checked at component level to prevent transitive identity/assertion conflicts and ambiguous bridge attribution.
- High-risk untrusted content can be kept, quarantined, or dropped by explicit policy; quarantined content does not enter synthesis.
- Filter audit is an internal consistency gate, not a semantic-truth or security proof.
## v2.3 context safety and recall boundary

- Recall operates only on repository entries admitted to the local repository index; it does not contact a memory provider or an LLM.
- Recalled repository text remains `evidence-only` and never gains instruction authority.
- HOT evidence is revision-bound. Git blob identity is preferred when available; changed/missing evidence is invalidated before reuse.
- The Context Store is an overlay, not an archive: it does not persist full source text or a duplicate WARM repository index.
- Local source search is bounded. `rg` is invoked as argv (`shell=False`) when available; the fallback scans only index-admitted files with file/result caps.
- A successful deterministic recall means relevant candidates were rehydrated under the configured rules; it is **not** proof that all semantically relevant evidence has been found. Low/no coverage is surfaced as an escalation signal rather than guessed away.
- `ContextEvidence` verification authorizes only deterministic conclusions. `unknown` is a valid result and must not be coerced into a merge.



## v2.4 claim-verification recall boundary

Claim-aware verification recall remains a local deterministic retrieval feature. Repository text, regex matches, and negative-search observations remain evidence-only and never gain instruction authority. `challenged` and `provisionally-supported` are routing/evidence states, not semantic truth claims. Negative evidence is considered meaningful only for a bounded, complete scope; an unavailable requested scope must not silently broaden to the entire repository.
