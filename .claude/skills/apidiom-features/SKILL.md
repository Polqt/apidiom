---
name: apidiom-features
description: Use when implementing or planning any apidiom feature. Contains the product direction, the 5-feature roadmap, full algorithmic detail, AI concepts, CLI design, and codebase design notes. Read before touching generate/, pipeline.py, or cli.py.
---

# apidiom Feature Roadmap

## What apidiom is (correct mental model)

**Direction: `OpenAPI spec → agent-ready tools`**

NOT "mcp → api". The project takes an *existing* REST API that already has an OpenAPI spec and generates the glue code that lets AI agents call it. The API already exists. The agent already exists. apidiom writes the wiring layer in seconds instead of hours.

```
Stripe publishes openapi/spec3.yaml
        ↓
apidiom generate mcp stripe.yaml
        ↓
server.py — 200+ @mcp.tool() functions
        ↓
Claude agent calls create_payment_intent(amount=5000, currency="usd")
```

**Core value:** 30 seconds to wire any OpenAPI-documented API into any AI agent, instead of 2-4 hours of hand-writing tool wrappers.

**Who uses it:** AI agent developers who need to connect their agent (Claude, LangChain, GPT-4, custom) to 3rd-party or internal REST APIs.

---

## The 4 agent runtime targets

Every feature must consider all 4:

| Runtime | Protocol | apidiom output | User imports |
|---|---|---|---|
| Claude Desktop / Anthropic API + MCP | MCP (stdio/SSE) | `server.py` with `@mcp.tool()` | Runs as subprocess |
| LangChain / LangGraph | Python functions | `tools.py` with `@tool` | `from tools import list_issues` |
| Anthropic SDK (raw tool_use) | JSON schema | `tools.json` anthropic format | Passes to `client.messages.create(tools=...)` |
| OpenAI SDK / Assistants | JSON schema | `tools.json` openai format | Passes to `client.chat.completions.create(tools=...)` |

---

## Core pipeline (shared by all features)

```
Source (file path, URL, or inline YAML/JSON)
        ↓
load_openapi_document()          ← ingest/openapi_ingest.py
normalize_openapi_document()     ← → APIClientModel
        ↓
Generator (format-specific)
  ├── mcp.py          → mcp_server.py.j2    → server.py
  ├── langchain_gen.py → langchain_tools.py.j2 → tools.py
  └── schema_gen.py   → JSON (no template)  → tools.json
        ↓
PipelineResult
        ↓
write_output()                   ← output/writer.py
```

**Key invariant:** Parsing happens once. All generators consume the same `APIClientModel`. Adding a new output format = new generator + new template, zero changes to ingest.

---

## Codebase design notes (deep module principles)

### Current shallow spots to fix

`_extract_body_params`, `_python_type`, `_safe_parameter_name` live in `mcp.py` but will be needed by `langchain_gen.py` and `schema_gen.py`. Extract to `generate/type_utils.py` when the second consumer appears (don't prematurely extract before LangChain exists).

### Interface design

`generate_mcp_server(spec, model)` takes two args — both needed because callers sometimes pre-load the model (perf) and sometimes don't. Keep both; add a convenience `generate_mcp_server_from_source(source)` in pipeline.py if the 2-arg form becomes a caller burden.

### Seam placement

The seam is at `PipelineResult` — callers don't know if the source was a file, URL, or inline YAML. The generator doesn't know where output goes. Keep it that way.

---

## Feature 1: LangChain Tools Generator

**Status:** Planned. Implement after current MCP feature is stable.

### Problem
LangChain has 10× the installed base of MCP in Python agent ecosystem. Devs building LangChain/LangGraph agents have no fast path to wire external APIs.

### CLI
```bash
apidiom generate langchain stripe.yaml --output stripe_tools.py
apidiom generate langchain stripe.yaml --tag payments --output payments.py
apidiom generate langchain stripe.yaml --include POST:/v1/charges
```

### Output shape
```python
from __future__ import annotations
import os
from typing import Any
import httpx
from langchain_core.tools import tool

DEFAULT_BASE_URL = "https://api.stripe.com"
API_BASE_URL = os.environ.get("APIDIOM_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

def _request_json(method, path, *, params=None, json_body=None, headers=None) -> dict[str, Any]:
    ...  # same helper as MCP server

@tool
def create_charge(amount: int, currency: str, description: str | None = None) -> dict[str, Any]:
    """Create a charge on Stripe. amount in smallest currency unit (cents)."""
    ...

@tool
def list_customers(limit: int | None = None, email: str | None = None) -> dict[str, Any]:
    """List all Stripe customers with optional filters."""
    ...
```

### AI concept
**Agentic loop:** LangChain agent executor runs LLM → picks @tool → executes → feeds result back → repeat. Each @tool is one API endpoint. LangGraph adds explicit state machines (nodes + edges) around this loop for multi-step workflows like "charge customer → send receipt → update CRM".

**Tool selection:** LLM reads the function name + docstring to decide which tool to call. Quality of description determines agent accuracy. `list_customers` + good docstring > vague `get_data`.

### Algorithm
1. Same `_load_openapi_source` → `APIClientModel` as MCP
2. For each endpoint: `_extract_body_params` → typed params OR `body: dict` fallback
3. Render `langchain_tools.py.j2` — identical logic to `mcp_server.py.j2` but `@tool` instead of `@mcp.tool()`
4. No `FastMCP` setup, no `mcp.run()` — just importable functions

### Files
- `src/apidiom/generate/langchain_gen.py` (new)
- `src/apidiom/generate/templates/langchain_tools.py.j2` (new)
- `src/apidiom/pipeline.py` — add `generate_langchain_tools()`
- `src/apidiom/cli.py` — add `langchain` dispatch in `generate` command
- `tests/test_langchain_gen.py` (new)

### Python packages
- `langchain-core` — user installs, NOT in apidiom's dependencies
- No new apidiom deps

### No changes needed
pipeline.py ingest, writer.py, models.py

---

## Feature 2: JSON Schema Export

**Status:** Planned.

### Problem
Devs using raw Anthropic or OpenAI SDK (no framework) need tool schemas in the exact JSON format each provider expects. Currently they write these by hand.

### CLI
```bash
apidiom generate schema stripe.yaml --format anthropic --output tools.json
apidiom generate schema stripe.yaml --format openai    --output tools.json
apidiom generate schema stripe.yaml --format anthropic  # → stdout
```

### Output shape (Anthropic format)
```json
[
  {
    "name": "create_charge",
    "description": "Create a charge on Stripe.",
    "input_schema": {
      "type": "object",
      "properties": {
        "amount": {"type": "integer", "description": "Amount in cents"},
        "currency": {"type": "string"},
        "description": {"type": "string"}
      },
      "required": ["amount", "currency"]
    }
  }
]
```

### Output shape (OpenAI format)
```json
[
  {
    "type": "function",
    "function": {
      "name": "create_charge",
      "description": "Create a charge on Stripe.",
      "parameters": {
        "type": "object",
        "properties": { ... },
        "required": ["amount", "currency"]
      }
    }
  }
]
```

### AI concept
**Tool use / function calling:** The lowest-level form of agent tool access. The LLM receives a list of tool schemas, decides which one to call, outputs a structured tool_use block, and your code executes it. No framework. You own the loop. This is what LangChain and MCP both implement under the hood.

### Algorithm
1. Same `APIClientModel` pipeline
2. For each endpoint: extract params + body schema → build JSON schema dict
3. Wrap in format-specific envelope (anthropic: flat list; openai: `{type: function, function: {...}}`)
4. `json.dumps(indent=2)` → stdout or file (no Jinja2 needed)

### Files
- `src/apidiom/generate/schema_gen.py` (new)
- `src/apidiom/pipeline.py` — add `generate_tool_schema()`
- `src/apidiom/cli.py` — add `schema` dispatch
- `tests/test_schema_gen.py` (new)

### Python packages
None new.

---

## Feature 3: URL Spec Auto-Discovery

**Status:** Planned.

### Problem
Dev has the API's base URL but not the spec file path. Currently they have to manually find it. Auto-discovery removes a manual step and enables `apidiom generate mcp https://api.stripe.com` to just work.

### CLI
```bash
# Current (requires knowing spec path):
apidiom generate mcp https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.yaml

# With auto-discovery:
apidiom generate mcp https://api.stripe.com
apidiom generate mcp https://api.stripe.com --discover  # explicit flag
```

### Algorithm
```python
DISCOVERY_PATHS = [
    "/openapi.json",
    "/openapi.yaml",
    "/swagger.json",
    "/swagger.yaml",
    "/api-docs",
    "/api-docs.json",
    "/api/openapi.json",
    "/api/swagger.json",
    "/.well-known/openapi.json",
    "/v1/openapi.json",
    "/v2/openapi.json",
    "/v3/openapi.json",
]

def discover_openapi_spec(base_url: str) -> str | None:
    """Try common paths. Return first URL that returns a valid OpenAPI doc."""
    for path in DISCOVERY_PATHS:
        url = base_url.rstrip("/") + path
        try:
            r = httpx.get(url, timeout=5, follow_redirects=True)
            if r.status_code == 200 and _looks_like_openapi(r.text):
                return url
        except httpx.HTTPError:
            continue
    return None

def _looks_like_openapi(text: str) -> bool:
    try:
        doc = yaml.safe_load(text)
        return isinstance(doc, dict) and (
            "openapi" in doc or "swagger" in doc
        )
    except Exception:
        return False
```

### AI concept
**API discovery for autonomous agents:** An agent that can discover and consume new APIs without human configuration is a step toward autonomous tool acquisition. This feature is the human-assisted version — you give the base URL, apidiom finds the spec. Future: agents could call `discover_openapi_spec` themselves.

### Files
- `src/apidiom/ingest/discovery.py` (new) — `discover_openapi_spec()`
- `src/apidiom/pipeline.py` — call discovery when input looks like a base URL (no file extension, no common spec path)
- `tests/test_discovery.py` (new)

### Python packages
- `httpx` — already installed

---

## Feature 4: Multi-Spec Merge

**Status:** Planned.

### Problem
A complex agent needs tools from multiple APIs (Stripe for payments + GitHub for code + Slack for notifications). Currently: run apidiom 3 times, get 3 servers, configure agent with 3 MCP connections. Multi-spec merge → one unified server.

### CLI
```bash
apidiom generate mcp stripe.yaml github.yaml slack.yaml --output unified_mcp/
apidiom generate langchain stripe.yaml github.yaml --output multi_tools.py
```

### Algorithm
```python
def merge_models(models: list[APIClientModel]) -> APIClientModel:
    """Merge N APIClientModels into one. Deduplicate by operation_id."""
    seen_ops: set[str] = set()
    merged_endpoints: list[APIEndpoint] = []
    merged_auth: list[AuthScheme] = []
    seen_auth: set[str] = set()

    for model in models:
        for endpoint in model.endpoints:
            key = endpoint.operation_id or f"{endpoint.method}:{endpoint.path}"
            if key not in seen_ops:
                seen_ops.add(key)
                merged_endpoints.append(endpoint)
        for scheme in model.auth_schemes:
            if scheme.name not in seen_auth:
                seen_auth.add(scheme.name)
                merged_auth.append(scheme)

    return APIClientModel(
        title="merged",
        endpoints=merged_endpoints,
        auth_schemes=merged_auth,
    )
```

### AI concept
**Multi-agent orchestration:** A coordinator LLM dispatches subtasks to specialized agents, each with their own tool subset. OR a single agent has all tools from multiple APIs in one MCP server and decides which to call. Multi-spec merge enables the "one server, many APIs" pattern without running multiple servers.

**Agentic workflow example:**
```
User: "Charge the customer who filed issue #42 and notify them in Slack"
Agent (with merged server):
  → get_issue(42)           # GitHub tool
  → create_charge(...)      # Stripe tool
  → post_message(...)       # Slack tool
```

### Files
- `src/apidiom/ingest/merge.py` (new) — `merge_models()`
- `src/apidiom/pipeline.py` — accept `list[str | Path]` sources
- `src/apidiom/cli.py` — accept multiple positional args for `generate mcp`
- `tests/test_merge.py` (new)

### Python packages
None new.

---

## Feature 5: LLM Docstring Enrichment

**Status:** Planned.

### Problem
Many OpenAPI specs have sparse or missing descriptions. `summary: "Create charge"` alone gives the LLM little to work with when deciding which tool to call. Better docstrings → better agent tool selection.

### CLI
```bash
apidiom generate mcp sparse.yaml --enrich-docs --provider gemini --output server.py
apidiom generate mcp sparse.yaml --enrich-docs --provider ollama:llama3 --output server.py
```

### Algorithm
```python
def enrich_description(endpoint: APIEndpoint, provider: LLMProvider) -> str:
    """Use LLM to write a better tool docstring for sparse endpoints."""
    if _description_is_rich_enough(endpoint):
        return endpoint.summary or ""  # skip LLM call if already good

    prompt = f"""
    Write a 1-2 sentence description for an AI agent tool that wraps this API endpoint.
    Method: {endpoint.method}
    Path: {endpoint.path}
    Summary: {endpoint.summary or 'none'}
    Parameters: {[p.name for p in endpoint.path_parameters + endpoint.query_parameters]}
    Body: {endpoint.request_schema.value if endpoint.request_schema else 'none'}

    Write ONLY the description. No quotes. No prefix.
    """
    return provider.complete(prompt).strip()

def _description_is_rich_enough(endpoint: APIEndpoint) -> bool:
    description = endpoint.summary or ""
    return len(description.split()) >= 8  # 8+ words = rich enough
```

### AI concept
**LLM-augmented code generation:** Using an LLM not as the agent but as a code generation assistant. The generated docstring becomes part of the tool schema that a *different* LLM (the agent) reads at runtime. LLM writes docs → LLM reads docs → better tool selection.

**Why this matters for agent accuracy:** Tool selection in function-calling LLMs is heavily influenced by the tool's name and description. A vague description causes tool misuse or non-use. This feature makes every generated tool more agent-friendly.

### Files
- `src/apidiom/generate/enrichment.py` (new) — `enrich_description()`
- `src/apidiom/generate/mcp.py` — accept optional `enricher` callable
- `src/apidiom/generate/langchain_gen.py` — same
- `src/apidiom/pipeline.py` — wire enricher when `--enrich-docs` flag set
- `src/apidiom/cli.py` — add `--enrich-docs` + `--provider` to generate commands
- `tests/test_enrichment.py` (new)

### Python packages
- Uses existing LLM provider infrastructure (`llm/provider.py`)
- No new deps

---

## Implementation order

```
Feature 1 (LangChain)     ← 1 day  — highest installed base
Feature 2 (JSON schema)   ← 0.5 day — unlocks raw SDK users
Feature 3 (URL discovery) ← 0.5 day — UX improvement, standalone
Feature 4 (Multi-spec)    ← 1 day  — requires Features 1+2 to be useful
Feature 5 (Enrichment)    ← 1 day  — standalone, can go any time
```

---

## Shared utilities to extract (when Feature 1 lands)

Move from `mcp.py` to `generate/type_utils.py`:
- `_python_type(schema)` — OpenAPI type → Python annotation string
- `_extract_body_params(schema)` — simple object decomposition
- `_safe_parameter_name(name)` — keyword-safe identifier

Move from `mcp.py` to `generate/endpoint_utils.py`:
- `_path_expression(path, params)` — `/foo/{id}` → f-string
- `_description(endpoint)` — summary fallback
- `_auth_headers(endpoint, schemes)` — auth header list

**Don't extract until Feature 1 creates the second consumer (YAGNI).**

---

## Verification commands (run after each feature)

```bash
ruff check src tests
ruff format --check src tests
mypy
pytest
```

All four must pass. No exceptions.
