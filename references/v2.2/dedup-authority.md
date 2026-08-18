# Dedup Authority

Merge authority is deliberately narrow. Exact normalized claims and exact deterministic identity + structured assertion sides can authorize candidate merges. Similarity cannot. `canonicalKey` identifies a fact; without `value/polarity`, production mode requires exact normalized claim equality. A component-level guard prevents pair-wise-safe edges from creating an unsafe transitive component. Identity-less bridges that touch conflicting identities/assertion sides are left separate.
