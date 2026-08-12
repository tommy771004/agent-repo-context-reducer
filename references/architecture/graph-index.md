# Architecture: Persistent Graph Index

`.repo-context/index.json` stores the repository's compact structural index.

It contains:
- files and structural summaries,
- indexed symbol definitions with line ranges and fingerprints,
- resolved static file-import edges and reverse edges,
- entry points, manifests, languages, workspaces, and framework hints.

The graph intentionally does not claim complete runtime call relationships. Dynamic imports, reflection, dependency injection, runtime module resolution, metaprogramming, and generated code may be unresolved.

`sync` uses file metadata and a summary cache to avoid reparsing unchanged source whenever possible, then refreshes the graph view.
