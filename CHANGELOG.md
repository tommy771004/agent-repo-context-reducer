# Changelog

## 0.2.0

- Progressive Top-K output instead of emitting every file summary by default.
- Task-aware `query` ranking.
- Local import/dependency graph and reverse dependencies.
- Entry-point distance and graph centrality ranking signals.
- Git-aware file discovery with `.gitignore` support.
- `changed` mode for Git changes and affected dependency neighborhoods.
- `module` and `deps` drill-down commands.
- Python AST structural parser plus improved multi-line/language-aware heuristics.
- Monorepo/workspace detection.
- Incremental structural-summary cache.
- Secret, symlink, generated, binary and oversized-file guards.
- Optional installable `repo-context` Python CLI.
- Expanded cross-platform tests and documentation.

## 0.1.0

- Initial repository structural scanner and Agent Skill.
