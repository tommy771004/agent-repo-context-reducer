# Filter Audit

`repo-context filter-audit <reduction.json>` checks internal reducer invariants: support counts, duplicate accounting, candidate merge authority, contradiction-side retention, component-block accounting, and final statistics. Exit code 3 means the invariant gate failed. The audit is deterministic and cannot prove that a claim is true. Runtime execution applies the same gate before synthesis and finalization.
