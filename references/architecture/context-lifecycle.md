# Context Lifecycle

Context lifecycle is harness metadata:

- HOT: currently active context
- WARM: recently useful summary/reference
- COLD: historical reference; rehydrate only when needed
- INVALID: source fingerprint changed

The CLI can demote items between tiers and avoid re-emitting unchanged content. It cannot remove tokens that are already inside an LLM request or provider-managed conversation history.
