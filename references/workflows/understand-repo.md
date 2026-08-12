# Workflow: Understand Repository

Use for architecture, onboarding, project overview, module boundaries, or "read the whole repo" requests.

1. Use the provider resolution returned by `repo-context route`.
2. If a compatible architecture/graph/index provider is available, reuse it and pass its JSON through `repo-context ingest/context --external`.
3. Build/sync the native index only for unresolved native-fallback capabilities.
4. Generate a bounded context pack with the exact user task.
5. Describe architecture from manifests, entry points, workspaces, central files and evidence-backed dependency paths.
6. Expand one module or symbol at a time only for a concrete unresolved question.
7. Do not recursively read every source file to claim repository understanding.

Read `../policies/context-budget.md` and `../policies/progressive-reading.md` when additional context is needed.
