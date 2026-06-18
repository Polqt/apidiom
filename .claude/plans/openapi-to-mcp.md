# Plan: OpenAPI → MCP Server Generator

**Goal:** `apidiom mcp <spec>` → runnable MCP server Python file wrapping any external API.

**Distinct from** `apidiom.mcp.server` (apidiom AS an MCP server). This generates a NEW MCP server file that wraps an external API.

---

## Reuse (do NOT reimplement)

| Existing | Location | Use for |
|---|---|---|
| `_function_name(endpoint)` | `generate/codegen.py:314` | tool function names |
| `_safe_identifier()` | `generate/codegen.py:369` | Python-safe param names |
| `_path_expression()` | `generate/codegen.py:323` | f-string path interpolation |
| `write_output()` | `output/writer.py` | `--output`, `--clipboard`, stdout |
| `load_openapi()` | `ingest/openapi_ingest.py` | parse spec → `APIClientModel` |
| `FastMCP` | already in `mcp[extra]` in pyproject.toml | MCP server runtime |
| Jinja2 `Environment` | `generate/codegen.py:199` | template rendering |

---

## Day 1 — Core Generator (library only, no CLI)

### 1. Type map helper (10 min)
`src/apidiom/generate/mcp_generator.py`

```python
_OPENAPI_TO_PYTHON: dict[str, str] = {
    "string": "str", "integer": "int", "number": "float",
    "boolean": "bool", "array": "list", "object": "dict",
}

def _py_type(schema: OpenAPISchema | None) -> str:
    if schema is None:
        return "Any"
    return _OPENAPI_TO_PYTHON.get(schema.value.get("type", ""), "Any")
```

### 2. Template context dataclasses (20 min)
```python
@dataclass(frozen=True)
class _MCPParam:
    name: str          # original param name (for httpx)
    safe_name: str     # Python-safe identifier
    py_type: str       # str | int | float | bool | list | dict | Any
    required: bool

@dataclass(frozen=True)
class _MCPEndpoint:
    function_name: str
    method: str        # lowercase
    path_expression: str
    params: list[_MCPParam]          # path + query (for signature)
    query_params: list[_MCPParam]    # query only (for params= dict)
    has_body: bool
    docstring: str
```

### 3. Jinja2 template
`src/apidiom/generate/templates/mcp_server.py.j2`

```jinja
from __future__ import annotations
from typing import Any
import os
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("{{ api_name }}")

_BASE_URL = os.environ.get("{{ env_prefix }}_BASE_URL", "{{ base_url }}")
_AUTH_TOKEN = os.environ.get("{{ env_prefix }}_AUTH_TOKEN", "")
_HEADERS: dict[str, str] = {"Authorization": f"Bearer {_AUTH_TOKEN}"} if _AUTH_TOKEN else {}

{% for ep in endpoints %}
@mcp.tool()
def {{ ep.function_name }}(
{% for p in ep.params -%}
    {{ p.safe_name }}: {{ p.py_type }}{% if not p.required %} = None{% endif %},
{% endfor -%}
{% if ep.has_body %}
    body: dict[str, Any] | None = None,
{% endif -%}
) -> Any:
    """{{ ep.docstring }}"""
    response = httpx.{{ ep.method }}(
        f"{_BASE_URL}{{ ep.path_expression }}",
{% if ep.query_params %}
        params={ {% for p in ep.query_params %}"{{ p.name }}": {{ p.safe_name }}, {% endfor %}},
{% endif %}
{% if ep.has_body %}
        json=body,
{% endif %}
        headers=_HEADERS,
    )
    response.raise_for_status()
    return response.json() if response.content else {}

{% endfor %}
if __name__ == "__main__":
    mcp.run()
```

### 4. Public function
```python
def generate_mcp_server(model: APIClientModel) -> str:
    """APIClientModel → MCP server Python source."""
    ...  # render template
```

### 5. Tests (write first — see AGENTS.md)
`tests/test_mcp_generator.py`

- Given petstore `APIClientModel` → output contains `@mcp.tool()`
- Each endpoint becomes a function
- Path params in signature, typed
- Query params in `params=` dict
- Body endpoints have `body: dict | None`
- `_BASE_URL` / `_AUTH_TOKEN` env vars present
- No auth endpoints still have env var stubs

---

## Day 2 — CLI Command + Integration

### 6. CLI command (30 min)
Add to `src/apidiom/cli.py`:

```python
@main.command()
@click.argument("source")
@click.option("--output", type=click.Path(path_type=Path), default=None)
@click.option("--clipboard", is_flag=True)
@click.option("--force", is_flag=True)
def mcp(ctx, source, output, clipboard, force):
    """Generate an MCP server wrapping an external API.

    Example:
      apidiom mcp https://petstore3.swagger.io/api/v3/openapi.json --output petstore_mcp.py
    """
    from apidiom.generate.mcp_generator import generate_mcp_server
    from apidiom.ingest.openapi_ingest import OpenAPIIngestError, load_openapi

    try:
        model = load_openapi(source)
        code = generate_mcp_server(model)
    except (OpenAPIIngestError, RuntimeError, ValueError) as exc:
        _fail(str(exc))
        return

    # reuse existing output machinery
    from apidiom.output.writer import OutputError, write_output
    from apidiom.pipeline import PipelineResult
    result = PipelineResult(spec={}, model=model, generated_client=code,
                            generated_files={"mcp_server.py": code}, ...)
    write_output(result, output=output, clipboard=clipboard, force=force, ...)
```

> Note: check `write_output` signature — may need a thin adapter if `PipelineResult` is too coupled.

### 7. Integration test
`tests/test_cli_mcp.py` — `CliRunner` invoking `apidiom mcp tests/fixtures/petstore.yaml`

### 8. Manual smoke test
```bash
apidiom mcp https://petstore3.swagger.io/api/v3/openapi.json --output petstore_mcp.py
python petstore_mcp.py  # should start without error
```

---

## Files to create

```
src/apidiom/generate/mcp_generator.py          ← new
src/apidiom/generate/templates/mcp_server.py.j2 ← new
tests/test_mcp_generator.py                    ← new
tests/test_cli_mcp.py                          ← new
src/apidiom/cli.py                             ← add mcp command
```

## Files NOT to touch

- `src/apidiom/mcp/server.py` — that's apidiom's OWN MCP server, unrelated
- `src/apidiom/models.py` — models are complete
- `pyproject.toml` — `mcp` extra already there

---

## Known ceiling

- No `$ref` resolution for request body schemas (just `body: dict | None`). Good enough for v1.
- No OAuth flows, only Bearer token via env var. Add when user asks.
- No streaming endpoints. Skip.
