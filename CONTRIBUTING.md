# Contributing

Contributions are welcome, especially for parser accuracy, dependency resolution, ranking quality and regression fixtures.

## Principles

- Keep the core runtime dependency-free unless an optional integration is clearly isolated.
- Prefer deterministic preprocessing over model calls.
- Do not increase output volume without a clear navigation benefit.
- Preserve safe defaults around secrets, symlinks and generated files.
- Add tests for parser or ranking changes.

## Test

```bash
python -m unittest discover -s tests -v
```

## Smoke test

```bash
python scripts/repo_context.py map examples/sample-project --top-k 5 --pretty
python scripts/repo_context.py query examples/sample-project "payment checkout" --top-k 5 --pretty
```
