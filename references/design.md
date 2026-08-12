# Design Notes

## Goal

The tool reduces codebase context before an AI coding agent consumes it. It scans files locally and emits compact structural metadata.

## Three-level reading strategy

### Level 1 — Project map

Collect:

- file tree statistics
- manifests
- languages
- entry-point candidates
- directory hot spots

### Level 2 — Structural context

Extract lightweight structure:

- imports
- exports
- classes
- interfaces/types/traits
- function and method signatures

### Level 3 — Full source

The agent opens full files only after the map points to a small relevant set.

## Why this saves context

A coding agent often needs to know *where* to look before it needs every implementation detail. Local deterministic scanning can answer the navigation question without sending every file body to the model.

## Correctness tradeoff

Heuristic parsing may miss multiline or unusual syntax. The tool is designed for routing and prioritization, not compilation or semantic verification.
