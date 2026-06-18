---
name: apidiom-style
description: Use when writing any code for the apidiom project — enforces project conventions for structure, testing, typing, and codegen patterns before touching files.
---

# apidiom Code Style & Conventions

## Project Shape

**Thin CLI, fat library.** Real logic lives in importable modules. CLI (`cli.py`) and web (`web/`) are thin wrappers only.

```
src/apidiom/
  ingest/          ← parse inputs → models
  generate/        ← models → code (Jinja2 templates)
    templates/     ← *.j2 files, one per output format
  mcp/             ← apidiom's own MCP server (thin)
  llm/             ← provider abstraction + pydantic-ai adapter
  output/          ← write_output(), clipboard, file I/O
  pipeline.py      ← orchestration: ingest → generate → return
  cli.py           ← click commands (thin)
  config.py        ← env var reads only
  models.py        ← frozen Pydantic models (source of truth)
```

## Rules

**Models:** All domain types in `models.py`. Frozen Pydantic. No mutation.

**Code generation:** Jinja2 template in `generate/templates/*.j2`. Generator function takes `APIClientModel`, returns `str`. Never build code strings with concatenation.

**Tests first.** AGENTS.md requires it. Write `tests/test_<module>.py` before implementation.

**No mocking of library internals.** Monkeypatch at module-level imports (`monkeypatch.setattr(server.pipeline, ...)`) not deep call chains.

**No new dependencies** without adding to `pyproject.toml` optional group AND `all` AND `dev`.

**Errors:** Raise specific exception classes (e.g., `OpenAPIIngestError`, `CodegenError`, `MCPToolError`). Never `Exception` directly. CLI catches and calls `_fail()`.

## Toolchain

```bash
ruff check src tests   # lint (E, F, I, UP, B rules)
ruff format src tests  # format (88 chars, py311)
mypy                   # strict — no Any escapes without cast()
pytest                 # tests/
```

**All four must pass** before a change is complete.

## Type discipline

- `from __future__ import annotations` at top of every new file
- `cast()` over `# type: ignore`
- `dict[str, Any]` for raw spec/JSON data only — use models everywhere else
- Protocol for injectable callbacks (see `SubprocessRunner` in `codegen.py`)

## Reusable helpers (don't reimplement)

| Helper | Location | Does |
|---|---|---|
| `_function_name(endpoint)` | `generate/codegen.py:314` | operationId → snake_case name |
| `_safe_identifier(s)` | `generate/codegen.py:369` | Python-safe identifier |
| `_path_expression(path)` | `generate/codegen.py:323` | `/foo/{id}` → f-string expr |
| `write_output(result, ...)` | `output/writer.py` | stdout / file / clipboard |
| `load_openapi(source)` | `ingest/openapi_ingest.py` | URL or file → `APIClientModel` |
| `get_provider(name)` | `llm/provider.py` | gemini / ollama / null |

## Test patterns

```python
# Fixture: tests/fixtures/petstore.yaml exists — use it
from apidiom.ingest.openapi_ingest import load_openapi
model = load_openapi("tests/fixtures/petstore.yaml")

# Monkeypatching pipeline (not httpx)
monkeypatch.setattr(server.pipeline, "generate_client", lambda *a, **k: fake_result)

# CLI testing
from click.testing import CliRunner
result = CliRunner().invoke(main, ["mcp", "tests/fixtures/petstore.yaml"])
assert result.exit_code == 0
```

## What NOT to add

- No databases, sessions, accounts, payments (AGENTS.md)
- No new CLI flags "for future use"
- No abstract base class with one implementation
- No config file parsing (env vars only, via `config.py`)
