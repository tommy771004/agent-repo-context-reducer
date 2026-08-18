# Streaming Fan-In

NDJSON/JSONL is the bounded-memory input mode. Each line is one worker output object. The reducer validates and aggregates it immediately, then discards the raw worker document.

State retained by `FanInAccumulator`:

- one aggregate per deterministic group/assertion side;
- supporting worker/source sets;
- trust counters;
- bounded malformed detail records;
- reducer metrics.

JSON-array input remains compatibility mode and is decoded as one document because the Python standard library has no incremental JSON-array parser.

Correctness does not change in streaming mode: grouping, agreement, contradiction surfacing and candidate authority remain deterministic.
