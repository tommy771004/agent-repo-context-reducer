# Critical Evidence Recall Benchmark

Token reduction is not sufficient evidence that context management works. v2.3 adds a deterministic benchmark that declares gold repository evidence per case and measures whether it can be recovered after the initial bounded context omits it.

Metrics:

- `initial_critical_evidence_recall`
- `final_critical_evidence_recall`
- `recall_gain`
- `missed_critical_evidence`
- `false_filter_rate`
- `model_calls_added_by_recall`

The bundled sample intentionally starts with context unrelated to three gold targets. Current sample result: initial recall `0.0`, final recall `1.0`, false-filter rate `0.0`, and `0` recall-added model calls. This is a small deterministic release fixture, not a claim of universal semantic recall.
