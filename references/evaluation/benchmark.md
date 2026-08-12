# Evaluation Policy

Do not optimize token reduction in isolation.

Track where possible:

- selected context tokens
- raw repository token estimate
- files/symbols selected
- expected-path recall for benchmark fixtures
- tool-call count
- latency
- answer correctness from an independent evaluator

Expected-path recall is not answer correctness. A system that reads nothing can save 100% of tokens and still be useless.

The target metric is closer to **correctness per token** than token reduction alone.
