# apidiom

> Turn any OpenAPI spec into an MCP server in one command.

```bash
npx apidiom generate mcp stripe --output stripe-mcp.js
node stripe-mcp.js
```

Point Claude Desktop (or any MCP client) at the generated file — your AI agent can now call Stripe directly.

## Quick Start

```bash
npm install -g apidiom
# or without installing:
npx apidiom generate mcp stripe --output stripe-mcp.js
```

Requires **Node.js 18+**.

## How it works

1. **Fetch** — downloads the OpenAPI spec from a URL, local file, or built-in registry
2. **Parse** — extracts endpoints, parameters, auth schemes, and the server URL
3. **Generate** — emits a single self-contained JS file that speaks the MCP protocol over stdio

## Usage

```bash
# Generate from a built-in service
apidiom generate mcp stripe --output stripe-mcp.js

# From a local OpenAPI spec
apidiom generate mcp ./my-api.yaml --output my-api-mcp.js

# From a URL
apidiom generate mcp https://example.com/openapi.yaml --output out.js

# Export raw SDK tool schemas
apidiom generate schema petstore --format anthropic --output tools.json
apidiom generate schema petstore --format openai --output tools.json

# Filter to a tag or specific operations
apidiom generate mcp github --tag repos
apidiom generate mcp openai --include createChatCompletion --output openai-mcp.js
apidiom generate schema petstore --format anthropic --tag pets
apidiom generate schema github --format anthropic --group-by-tag --output tools.json

# stdout (pipe-friendly; on Windows PowerShell use --output instead of >)
apidiom generate mcp petstore

# List built-in services
apidiom generate mcp --list
```

## Project Config (apidiom.yaml)

For projects integrating multiple APIs, use a config file instead of flags:

```bash
apidiom init                        # scaffold apidiom.yaml in current directory
apidiom run                         # generate all targets
apidiom run discord                 # generate single target
apidiom run --dry-run               # preview what would be generated without writing files
apidiom run --config path/to/apidiom.yaml
```

`apidiom.yaml` format:

```yaml
targets:
  discord:
    source: discord          # registry name, URL, or file path
    output: mcp/discord.js
    mode: search             # flat | search | auto (default: auto)
  stripe:
    source: stripe
    output: mcp/stripe.js
    tags: [payments, billing]
```

Output directories are created automatically.

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
| `slack` | Slack Web API |
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
- Relative server URLs in the spec (e.g. `/api/v3`) are resolved against the spec's origin when fetched over HTTP
- Per-request timeout (default 30s, override with `APIDIOM_TIMEOUT_MS`)
- **Flat mode** (default for small APIs): all tools exposed in `tools/list`
- **Search mode** (auto for large APIs): two meta-tools — `search_tools` and `call_tool` — replace the full list; auto-switches when tool count exceeds 40

Auth env var names are derived from the security scheme name:
`STRIPE_BEARER_TOKEN`, `GITHUB_BEARER_TOKEN`, `OPENAI_BEARER_TOKEN`, etc.

**Base URL override** — set `APIDIOM_BASE_URL` to point the generated server at a different origin (staging, self-hosted, or when a local spec has no absolute server URL):

```json
"env": { "APIDIOM_BASE_URL": "https://api-staging.example.com", "STRIPE_BEARER_TOKEN": "sk_test_..." }
```

## Generated Tool Schemas

`generate schema` writes portable JSON tool definitions for raw Anthropic or OpenAI SDK usage. Auth is not included in schema JSON; your execution code owns API credentials.

## Known Limitations

- External `$ref` files not supported (only `#/components/...` inline refs) — a warning is printed and the ref is skipped
- OAuth2 / OpenID Connect not supported in generated code
- Local specs with a relative-only server URL and no absolute origin: set `APIDIOM_BASE_URL` when running the generated server (it fails fast with a clear message otherwise)

## Add a Service

Edit `ts/registry.json` and open a PR:

```json
"my-service": { "url": "https://...", "description": "My Service API" }
```

## License

MIT
