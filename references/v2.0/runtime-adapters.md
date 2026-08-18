# v2.0 Runtime Adapters

v2.0 separates deterministic planning/context engineering from actual worker execution.

## Contract

Every worker receives `repo-context-runtime-invocation/v1` containing task, role, node id, abstract model tier, dependency handoffs, lane-sliced repository context, lane budget and an explicit untrusted-content policy.

Adapters return either a raw JSON payload or a normalized runtime result. Model/vendor selection is adapter-owned; the core runtime never assumes a concrete vendor model.

## Native subprocess adapter

The built-in adapter:

- requires explicit external-command authorization;
- uses argv with `shell=False`;
- sends one JSON invocation over stdin;
- expects one JSON value on stdout;
- uses a minimized environment unless `inherit_env=true` is explicitly configured;
- enforces timeout/cancellation;
- incrementally drains output and terminates a worker when stdout exceeds the cap.

It is not a sandbox and does not isolate filesystem/network access or descendant processes.

## Host adapters

A host may register an in-process adapter through Python. CLI input cannot point at an arbitrary module to import, avoiding an implicit code-execution surface.
