# Synthesis Packet

The synthesis packet is the final bounded context emitted after fan-in reduction.

## Ordering

Findings are selected by:

1. confidence descending,
2. agreement count descending,
3. stable claim ordering.

Contradictions are mandatory and are never silently dropped to satisfy the token target.

## Overflow

If mandatory contradiction evidence plus fixed metadata already exceed the target, the packet reports:

```json
{
  "budget": {
    "overflow": true,
    "overflow_reason": "mandatory contradiction/metadata sections exceed target"
  }
}
```

This is deliberate. Budget compliance must not be achieved by hiding unresolved evidence.

## Token estimate

The project continues to use its existing deterministic `UTF-8 bytes / 4` estimate. It is a planning approximation, not a provider billing guarantee.
