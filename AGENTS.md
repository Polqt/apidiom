# Agent Instructions

Build `apidiom` as a small, well-tested, open-source TypeScript developer tool.

- Keep real behavior in importable TypeScript modules under `ts/`.
- Keep CLI code thin; command handling should call library modules.
- Prefer the simplest implementation that satisfies the current phase.
- Do not add paid services, accounts, databases, payments, sessions, or scope outside the current phase.
- Validate new behavior with tests before implementation.
- Never commit or push; the user handles all git operations.

## Product Direction

**apidiom direction: `OpenAPI spec -> agent-ready tools`**

Takes any existing REST API with an OpenAPI spec and generates the wiring layer
that lets AI agents call it in seconds.

Current active runtime: Node.js / TypeScript.

Current output:
- `apidiom generate mcp <spec|service|url>` -> standalone JavaScript MCP server

Planned output formats:
- `apidiom generate schema <spec> --format anthropic|openai`
- `apidiom generate langchain <spec>` only if the project later reopens a Python target

## Active Features

### Done
- `apidiom generate mcp <spec|service|url>`
  - Built-in registry services
  - Local file and URL OpenAPI input
  - `$ref` resolution for parameters and request bodies
  - `--tag` and `--include` filters
  - `--group-by-tag` for tool name disambiguation
  - API key and bearer/basic auth env var wiring

### Next To Improve
1. Stabilize TS MCP generator and source resolution.
2. Add JSON schema export for raw Anthropic/OpenAI SDK users.
3. Add URL spec auto-discovery.
4. Add multi-spec merge.
5. Consider LLM docstring enrichment after generator targets are stable.

## Codebase Map

```text
ts/
  cli.ts                 <- thin Commander CLI
  registry.ts            <- built-in service registry and source resolution
  auth.ts                <- OpenAPI auth scheme -> generated env var config
  model.ts               <- TypeScript domain model
  ingest/
    fetch.ts             <- source -> OpenAPI document
    parse.ts             <- OpenAPI document -> APIModel
    resolve.ts           <- local $ref resolution
  generate/
    mcp.ts               <- APIModel -> standalone MCP JavaScript server
ts-tests/                <- active Vitest test suite
docs/                    <- documentation site
archive/python/          <- quarantined Python-era tests/config; not active
```

## Toolchain

All active checks must pass before done:

```bash
npm run build
npm run typecheck
npm test
```

Python-era code/tests are quarantined under `archive/python/` and are not part of
active verification unless the user explicitly reopens the Python target.
