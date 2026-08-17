# Capability resolution

Provider discovery examines compatible manifests, known safe CLI adapters and native capabilities. Description-only overlaps are informational. Machine execution requires a compatible adapter plus trust/policy approval. Unsupported capabilities resolve to `null` rather than fake native support.
