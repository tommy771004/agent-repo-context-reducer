# Process-tree cancellation

Native subprocess workers are started in a new POSIX session/process group. Timeout, output overflow and cancellation terminate the process group, then escalate to SIGKILL after a bounded grace period.

On Windows a new process group is requested and cleanup is best-effort, including `taskkill /T /F` when available after normal termination fails.

This is cleanup/backpressure behavior, not sandboxing. A process may still perform side effects before cancellation.
