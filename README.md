# apidiom

`apidiom` turns API documentation into idiomatic API clients.

Phase 0 only establishes the Python project scaffold: package metadata, CLI
entrypoint, linting, formatting, typing, tests, pre-commit, and CI.

## Development

```powershell
python -m pip install -e ".[dev]"
apidiom --help
ruff check .
ruff format --check .
mypy src
pytest
```

## Scope

This scaffold does not yet implement OpenAPI ingestion, LLM providers,
unstructured documentation extraction, code generation, output writing, or the
web UI.

