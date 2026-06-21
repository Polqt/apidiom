# apidiom

> Turn any OpenAPI spec into an MCP server in one command.

```bash
npx apidiom generate mcp stripe > stripe-mcp.js
node stripe-mcp.js
```

Point Claude Desktop (or any MCP client) at the generated file — your AI agent can now call Stripe directly.

## Quick Start

```bash
npm install -g apidiom
# or without installing:
npx apidiom generate mcp stripe > stripe-mcp.js
```

Requires **Node.js 18+**.

## Usage

```bash
# Generate from a built-in service
apidiom generate mcp stripe --output stripe-mcp.js

# From a local OpenAPI spec
apidiom generate mcp ./my-api.yaml --output my-api-mcp.js

# From a URL
apidiom generate mcp https://example.com/openapi.yaml --output out.js

# Filter to a tag or specific operations
apidiom generate mcp github --tag repos
apidiom generate mcp openai --include createChatCompletion

# List built-in services
apidiom generate mcp --list
```

## Connect to Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "stripe": {
      "command": "node",
      "args": ["/path/to/stripe-mcp.js"],
      "env": { "STRIPE_BEARER_TOKEN": "sk_test_..." }
    }
  }
}
```

## Built-in Services

| Name | Description |
|------|-------------|
| `stripe` | Stripe Payments API |
| `github` | GitHub REST API |
| `openai` | OpenAI API |
| `sendgrid` | SendGrid Email API |
| `pagerduty` | PagerDuty Incident Management API |
| `cloudflare` | Cloudflare API |
| `twilio` | Twilio Programmable API |
| `discord` | Discord HTTP API |
| `spotify` | Spotify Web API |
| `zoom` | Zoom Video Conferencing API |
| `notion` | Notion API |
| `jira` | Jira Cloud REST API |
| `vercel` | Vercel Deployment API |
| `petstore` | Petstore (demo) |

## Generated Server

Output is a **single self-contained JS file** — zero npm dependencies, Node.js built-ins only.

- MCP protocol over stdio (`initialize`, `tools/list`, `tools/call`)
- One MCP tool per API endpoint with full parameter schemas
- Auth read from env vars — fails fast with a clear error if missing
- `$ref` pointers in OpenAPI specs resolved automatically

Auth env var names are derived from the security scheme name:
`STRIPE_BEARER_TOKEN`, `GITHUB_BEARER_TOKEN`, `OPENAI_BEARER_TOKEN`, etc.

## Known Limitations

- External `$ref` files not supported (only `#/components/...` inline refs)
- OAuth2 / OpenID Connect not supported in generated code

## Add a Service

Edit `ts/registry.json` and open a PR:

```json
"my-service": { "url": "https://...", "description": "My Service API" }
```

## License

MIT

---

*Legacy Python docs below — kept for reference during transition.*

---

`apidiom` turns API documentation into idiomatic Python API clients.

The wedge: it can generate clients from messy docs that do not have a clean
OpenAPI spec, not just from already-valid OpenAPI documents. Unstructured docs
are extracted into a validated OpenAPI spec first, then client generation is
delegated to existing tools.

## Install

Install the core CLI:

```bash
python -m pip install apidiom
```

Install only the features you need:

```bash
python -m pip install "apidiom[gemini]"
python -m pip install "apidiom[ollama]"
python -m pip install "apidiom[codegen]"
python -m pip install "apidiom[web]"
python -m pip install "apidiom[mcp]"
```

Install every optional feature:

```bash
python -m pip install "apidiom[all]"
```

The Gemini and Ollama extras provide their HTTP client dependency. The
`codegen` extra provides the pure-Python fallback model generator. The primary
`openapi-generator-cli` path still requires Java and the external CLI.

### From source

For local development from this repository:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

On macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

The development extra installs all Python dependencies needed by the test
suite. If Java is unavailable, use `--codegen builtin` with the included
`datamodel-code-generator` development dependency.

## Quickstart

Generate from an existing OpenAPI spec:

```bash
apidiom generate ./openapi.yaml --output client.py --codegen builtin
```

Generate from messy documentation:

```bash
apidiom generate ./docs-page.html \
  --provider ollama \
  --output client.py \
  --codegen builtin
```

With no `--output` flag, generated code is printed to stdout. Use
`--clipboard` to copy the generated client instead.

Run the thin web UI:

```bash
uvicorn apidiom.web.app:app
```

The web UI is stateless: one page, no accounts, no database, no sessions, and no
server-side output files. It calls the same `pipeline.generate_client` entry
point as the CLI and returns either an HTMX result fragment or JSON from
`POST /generate?format=json`.

Run the MCP server:

```bash
python -m apidiom.mcp.server
```

Example MCP client config:

```json
{
  "mcpServers": {
    "apidiom": {
      "command": "python",
      "args": ["-m", "apidiom.mcp.server"]
    }
  }
}
```

The MCP `generate_client` tool accepts
`source, provider="null", lang="python", codegen="auto", input_kind=null`
and returns generated code, codegen tier, unverified fields, conflict notes, and
any Gemini privacy warning. Omit `input_kind` or pass `null` for shared
auto-detection. Use `input_kind="openapi"` or `input_kind="unstructured"` only
when you need an explicit override.

## Providers

`--provider` accepts:

- `null`: default; no LLM calls. Works only for already-structured OpenAPI
  input.
- `gemini`: cloud extraction through Gemini. Set `GEMINI_API_KEY`.
- `ollama`: local/offline extraction through an Ollama daemon.

Gemini free-tier data may be used for training. Use Gemini only for public
docs. Use Ollama for private or offline documentation.

Check readiness:

```bash
apidiom check --provider ollama
apidiom check --provider gemini
```

## Unverified Fields

`apidiom` is deliberately conservative. If docs do not explicitly state a type,
required flag, auth detail, server URL, or similar field, the generated OpenAPI
uses an unconstrained schema or marker instead of guessing.

Those uncertain fields are carried through as `x-apidiom-unknown` and
`UNVERIFIED` notes. The CLI prints a short warning summary after generation, and
the generated code includes `# UNVERIFIED:` comments so you can inspect and
confirm anything that was not grounded in the source docs.

## Optional Deploy

The included Dockerfile runs uvicorn on `0.0.0.0:$PORT`. It can deploy on a free
Render web service or Hugging Face Spaces; free instances may sleep when idle,
so expect roughly a one-minute cold start. Fly.io now requires a card.

The separate documentation site lives in `docs/` and builds to static files with
Astro/Starlight:

```bash
cd docs
npm install
npm run build
```

It can deploy for free as a static site to Cloudflare Pages or GitHub Pages.

## Development

```bash
ruff check .
ruff format --check .
mypy src
pytest
```
