# Unified Filter Pipeline

The v2.2 pipeline classifies malformed/low-confidence/trust-filtered input before deterministic grouping, then applies exact assertion grouping, optional candidate detection, deterministic pair verification, component compatibility, session/cross-layer filtering, and final budget selection. Every lossy stage exposes counters.

Decisions are KEEP, MERGE, DROP, QUARANTINE, CONTRADICTION, or REFERENCE_ONLY. Filtering does not silently convert malformed or quarantined material into consensus.
