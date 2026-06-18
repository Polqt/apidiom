# Agent Instructions

Build `apidiom` as a small, well-tested, open-source Python developer tool.

- Keep all real behavior in importable library code.
- Keep CLI and future web UI code thin.
- Prefer the simplest implementation that satisfies the current phase.
- Do not add paid services, accounts, databases, payments, sessions, or scope outside the current phase.
- Validate new behavior with tests before implementation.
- Never commit or push — the user handles all git operations.

## Skills

Project skills live in `.claude/skills/`. Cross-runtime copies in `~/.agents/skills/`. Read the relevant one before touching code.

- **`apidiom-style`** — conventions, toolchain, reusable helpers, test patterns. Read before writing any code.
- **`openapi-to-mcp`** — original feature spec for the OpenAPI → MCP generator.
- **`apidiom-features`** — full product roadmap: 5 features with algorithms, AI concepts, CLI design, codebase design notes. Read before implementing any new feature.

## Product direction (read this first)

**apidiom direction: `OpenAPI spec → agent-ready tools`**

Takes any existing REST API (Stripe, GitHub, Slack, your own backend) that has an OpenAPI spec and generates the wiring layer that lets AI agents call it in seconds.

Output formats:
- `apidiom generate mcp <spec>` → `@mcp.tool()` server for Claude / MCP-compatible agents
- `apidiom generate langchain <spec>` → `@tool` functions for LangChain / LangGraph agents
- `apidiom generate schema <spec> --format anthropic|openai` → JSON tool schemas for raw SDK use

## Active features (current HEAD: main)

### Done
- `apidiom generate mcp <spec>` — full MCP server generator with typed body params
  - Simple object request bodies decomposed into typed Python params (`amount: int, currency: str`)
  - Complex/array bodies fall back to `body: dict[str, Any] | None = None`
  - `--tag` and `--include` filters
  - `--list` to preview available operations
  - `--check` to validate generated server

### Next to implement (in order)

**Feature 1: LangChain Tools Generator**
- New files: `src/apidiom/generate/langchain_gen.py`, `src/apidiom/generate/templates/langchain_tools.py.j2`, `tests/test_langchain_gen.py`
- Pipeline: add `generate_langchain_tools()` to `pipeline.py`
- CLI: add `langchain` dispatch in `generate` command (mirror of `mcp` dispatch)
- Same typed body params logic as MCP — reuse `_extract_body_params` from `mcp.py`
- No new dependencies — `langchain-core` is user's dep, not apidiom's

**Feature 2: JSON Schema Export**
- New files: `src/apidiom/generate/schema_gen.py`, `tests/test_schema_gen.py`
- CLI: `apidiom generate schema <spec> --format anthropic|openai`
- No Jinja2 — pure `json.dumps()` output

**Feature 3: URL Spec Auto-Discovery**
- New file: `src/apidiom/ingest/discovery.py`
- Probes common paths (`/openapi.json`, `/swagger.json`, etc.) when input is a bare URL
- Uses existing `httpx` dep

**Feature 4: Multi-Spec Merge**
- New file: `src/apidiom/ingest/merge.py`
- CLI: `apidiom generate mcp spec1.yaml spec2.yaml` (multiple positional args)
- Deduplicates by operation_id

**Feature 5: LLM Docstring Enrichment**
- New file: `src/apidiom/generate/enrichment.py`
- CLI flag: `--enrich-docs --provider gemini|ollama`
- Uses existing LLM provider infrastructure

Full detail for all 5: read `apidiom-features` skill.

## Codebase map

```
src/apidiom/
  ingest/
    openapi_ingest.py     ← parse OpenAPI → APIClientModel
    discovery.py          ← (Feature 3) URL spec discovery
    merge.py              ← (Feature 4) multi-spec merge
  generate/
    mcp.py                ← MCP server generator (DONE)
    langchain_gen.py      ← (Feature 1) LangChain tools generator
    schema_gen.py         ← (Feature 2) JSON schema export
    enrichment.py         ← (Feature 5) LLM docstring enrichment
    type_utils.py         ← (extract when Feature 1 lands) shared type helpers
    codegen.py            ← shared helpers: _function_name, _safe_identifier
    templates/
      mcp_server.py.j2
      langchain_tools.py.j2  ← (Feature 1)
  output/writer.py        ← write_output() — file/stdout/clipboard
  pipeline.py             ← orchestration: ingest → generate → PipelineResult
  cli.py                  ← click commands (thin wrappers)
  models.py               ← frozen Pydantic models (source of truth)
  llm/provider.py         ← LLM provider abstraction
```

## Toolchain (all four must pass before done)

```bash
ruff check src tests
ruff format --check src tests
mypy
pytest
```
