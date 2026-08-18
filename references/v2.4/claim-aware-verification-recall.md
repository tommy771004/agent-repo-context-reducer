# Claim-Aware Verification Recall

v2.4 extends `Reduce → Verify → Recall` with a narrow post-hypothesis retrieval primitive.

## Goal

A locally plausible claim may be wrong because the current span hides a breakpoint override, runtime consumer, state persistence layer, translation leakage, dependency edge, or another contradictory implementation detail. Claim-aware recall asks **what repository evidence would confirm, challenge, or broaden this claim?** before a host promotes it.

## Control flow

```text
provisional claim
  -> deterministic requirement derivation
  -> scoped local repository checks
  -> compact positive / negative observations
  -> bounded evidence rehydration
  -> challenged | provisionally-supported | inconclusive
```

No LLM is required by this stage. The result never claims semantic truth. A host may continue with the current model, ask for another reasoning turn, or escalate only when the task warrants it.

## Safety invariants

1. Search relevance is not truth authority.
2. Missing scoped paths do not broaden silently to the entire repository.
3. An import is not proof of runtime invocation.
4. A base mobile class is not proof of desktop behavior; breakpoint evidence is checked separately.
5. A hard-coded copy hit is a challenge signal, not automatic proof of broken localization.
6. Evidence + compact observations share one model-visible token budget.
7. Rich requirement/search diagnostics remain in the local sidecar.
8. `semantic_truth_claimed` is always false in this contract.

## Trigger policy

Use claim-aware recall for risky, ambiguous, cross-file, or locally underdetermined claims. Do not execute it for every model sentence or every turn; that would replace context economy with verification overhead.
