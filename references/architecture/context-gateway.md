# Architecture: Context Gateway

The gateway sits before expensive model reasoning:

Repository -> Persistent Index -> Task Router -> Ranker -> Budget -> Session Dedup -> Minimal Context -> Agent

Deterministic layers handle filesystem guards, static imports, definitions, fingerprints, token estimates, and deltas. Heuristic layers handle task relevance, routing, lexical coverage, and expansion-stop recommendations.
