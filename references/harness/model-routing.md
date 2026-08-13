# Model Tier Routing

The reducer does not bind orchestration to Claude, GPT, Kimi, Gemini, or any other vendor model name.

## Deterministic first

Intent, task complexity, repository capability resolution, risk hints, duplicate detection, and simple routing are handled by deterministic code first. This costs zero model calls.

A model tier is considered only when work actually requires model reasoning.

## Abstract tiers

The runtime uses three abstract tiers:

- `cheap` — high-frequency, low-risk bounded work.
- `standard` — normal implementation and reasoning work.
- `strong` — expensive planning, grading, ambiguous or high-cost-of-error decisions.

A host or registered provider may map these tiers to concrete models. If no compatible `model.*` provider exists, tier resolution remains unresolved/advisory; the reducer does not invent a model mapping.

## Escalation inputs

Tier selection combines deterministic signals from:

- task complexity,
- risk / blast radius,
- ambiguity,
- novelty,
- cost of error.

High-risk, ambiguous, or novel work raises planner/grader tiers earlier than routine work.

## Sorter policy

The sorter is not a model by default. The built-in deterministic router performs classification with zero model calls. A cheap model is only a possible fallback when a host cannot resolve an ambiguous route deterministically; high-risk ambiguity must escalate beyond the cheap tier.

## Provider capability names

External runtimes can register:

- `model.cheap`
- `model.standard`
- `model.strong`

These are optional execution providers, not native reducer capabilities.
