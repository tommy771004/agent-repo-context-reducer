# v2.0 Telemetry and Final Evaluation

Per attempt, the runtime records latency and token usage. If a provider reports `input_tokens` / `output_tokens`, those values are labeled provider-reported; otherwise the configured tokenizer estimates them.

`cost_usd` is accepted only when reported by the provider/runtime response. The core has no embedded provider price table and never fabricates a dollar estimate.

Final-answer evaluation is deliberately narrow. It can check explicit required/forbidden phrases, required fields and an expected structured decision. Passing is not proof of semantic, factual or real-world correctness.
