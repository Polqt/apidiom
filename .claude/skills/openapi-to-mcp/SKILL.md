---
name: openapi-to-mcp
description: Use when building the apidiom MCP generator feature — generating MCP server code from OpenAPI specs, designing tool schemas, or implementing the `apidiom generate mcp` command.
---

# OpenAPI → MCP Server Generator (apidiom feature)

## The Problem

Agent builders need to connect AI agents to external APIs. Every time they do, they manually:
1. Read the API docs
2. Write a tool/function schema (JSON with LLM-readable descriptions)
3. Wire auth + error handling the agent can retry on
4. Repeat per endpoint

Current workarounds:
- Hand-write schemas in ChatGPT, paste in, fix manually (~20-30 min per API)
- `LangChain APIChain` — fragile, unmaintained
- Custom integration code per API

**Who:** Every developer building AI agents that call external services.

## The Feature

`apidiom generate mcp <spec>` → working MCP server Python file.

apidiom already parses OpenAPI → `APIClientModel`. This feature adds one generator:
walk `APIClientModel.endpoints`, emit an MCP server where each endpoint is a `@mcp.tool()`.

## What is MCP

**MCP = Model Context Protocol** — Anthropic's open standard for connecting LLMs/agents to tools and data. Claude, and increasingly all major agent frameworks, consume MCP servers.

An MCP server exposes:
- **Tools** — functions agents can call (our use case: one tool per API endpoint)
- **Resources** — data agents can read (not needed for v1)
- **Prompts** — reusable prompt templates (not needed for v1)

Transport: stdio (local) or SSE (remote). For v1, stdio is fine.

Python library: `fastmcp` (wraps the official `mcp` SDK, far less boilerplate).

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("stripe")

@mcp.tool()
def create_payment_intent(amount: int, currency: str) -> dict:
    """Create a PaymentIntent to track payment lifecycle."""
    # httpx call to POST /v1/payment_intents
    ...

if __name__ == "__main__":
    mcp.run()  # stdio transport
```

Agents discover tools by name + docstring. The docstring = the LLM's understanding of what this tool does. **Quality of description matters more than code.**

## MVP Scope (ship in 3-4 days)

**Input:** OpenAPI spec (URL or file path)  
**Output:** Single Python file — a runnable MCP server

Each `APIEndpoint` → one `@mcp.tool()` function:
- Function name: `operation_id` or `{method}_{path_slugified}`
- Docstring: `summary` + `description` from spec
- Parameters: typed Python args from `path_parameters` + `query_parameters` + `request_schema`
- Body: `httpx` call to the real endpoint
- Return: raw dict (agent parses it)

Auth: inject base URL + auth header as MCP server constructor params (or env vars).

**Secondary output (optional, +1 day):** `tool_schemas.json` in OpenAI/Anthropic function-calling format for non-MCP users.

## Project Context

apidiom codebase:
- `src/apidiom/ingest/openapi_ingest.py` — parses OpenAPI → `APIClientModel`
- `src/apidiom/models.py` — `APIClientModel`, `APIEndpoint`, `APIParameter`, `AuthScheme`
- `src/apidiom/generate/__init__.py` — empty, this is where the MCP generator goes
- `src/apidiom/llm/` — LLM providers (Gemini, Ollama) + pydantic-ai adapter
- Uses: `pydantic-ai`, `pydantic`, `httpx`, `openapi-spec-validator`, `yaml`

New dependency needed: `fastmcp` (or `mcp`)

## Pitch

> "Point apidiom at any OpenAPI spec, get a working MCP server your agents can use immediately."

Commodity: docs → typed client (`openapi-generator` does this)  
Unique: docs → agent-ready MCP server (nothing does this end-to-end cleanly)
