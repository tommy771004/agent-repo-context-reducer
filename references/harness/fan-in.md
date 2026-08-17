# Fan-In Reducer

## Purpose

The fan-in stage sits between parallel worker handoffs and the final reasoning/grading model.

It performs only deterministic reduction:

1. validate structured findings,
2. normalize conservative identity keys,
3. group only exact normalized claims or explicit canonical keys,
4. when structured value/polarity exists, split contradictory asserted sides inside the same fact identity,
5. keep the highest-confidence representative for each asserted side,
6. preserve agreement metadata only among workers supporting that same side,
7. surface structured value/polarity contradictions,
8. emit a bounded synthesis packet.

## Correctness rule

A missed duplicate wastes context. A false merge can erase evidence.

For that reason this layer does **not** use fuzzy text similarity or embeddings to merge findings. Semantic systems may nominate candidates upstream, but the final merge decision remains deterministic.

## Input

Worker outputs may contain `findings`, `evidence`, or a reduced `handoff` with evidence.

Preferred finding contract:

```json
{
  "claim": "Payment status updates asynchronously",
  "evidence": "src/services/payment.py:42",
  "source": "src/services/payment.py",
  "confidence": 0.91,
  "canonicalKey": "payment|status-update-mode",
  "subject": "payment-status",
  "predicate": "update-mode",
  "period": "current",
  "value": 1,
  "unit": "mode",
  "polarity": "async"
}
```

Only `claim`, `evidence`, and `source` are required.

## Output

The reducer returns:

```json
{
  "schema": "repo-context-fan-in/v1",
  "findings": [],
  "contradictions": [],
  "malformed": [],
  "stats": {},
  "provenance": {}
}
```

Keep `malformed` in logs/observability. Send `findings` plus `contradictions` through the synthesis-packet builder before invoking the final model.
