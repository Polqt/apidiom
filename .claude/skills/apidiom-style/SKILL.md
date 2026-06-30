---
name: apidiom-style
description: Use when writing any code for the apidiom project — enforces project conventions for structure, testing, typing, and codegen patterns before touching files.
---

# apidiom Code Style & Conventions

## Project Shape

**Thin CLI, fat library.** Real logic lives in importable TypeScript modules under `ts/`. CLI (`ts/cli.ts`) is a thin Commander wrapper only.

```
ts/
  cli.ts             ← thin Commander CLI; calls library modules
  model.ts           ← shared types (APIModel, APIEndpoint, AuthConfig …)
  auth.ts            ← extractAuth()
  registry.ts        ← REGISTRY, resolveSource()
  registry.json      ← built-in service entries
  ingest/
    fetch.ts         ← fetchSpec() — HTTP + local file load + ref resolution
    parse.ts         ← parseOpenAPI() — doc → APIModel
    resolve.ts       ← resolveRefs() — shallow $ref resolution
  generate/
    mcp.ts           ← generateMCPServer() → standalone CJS JS string
    schema.ts        ← generateToolSchema() → Anthropic/OpenAI JSON
    tools.ts         ← buildToolMetadata(), normalizeToolName(), enrichDescription()
    search.ts        ← scoreTools() — TypeScript scorer (mirrors generated JS scorer)

ts-tests/            ← Vitest tests; mirror ts/ directory structure
  fixtures/
    petstore.yaml
  cli.test.ts        ← CLI integration tests (spawn dist/cli.js)
  auth.test.ts
  registry.test.ts
  ingest/
    fetch.test.ts
    parse.test.ts
  generate/
    mcp.test.ts
    schema.test.ts
    search.test.ts
```

## Language & Toolchain

- TypeScript 5, strict mode, CommonJS output via tsup
- `npm run build` → `dist/cli.js`
- `npm run typecheck` → `tsc --noEmit`
- `npm test` → `vitest run`
- `npm run pack:smoke` → pack + run packed binary with `--version` to validate

## Key Conventions

- **Generated code is plain CJS JS** — no TypeScript, no frameworks, no bundler deps. Self-contained single file.
- **No `any`, no `@ts-ignore`**. Cast through `Doc = Record<string, unknown>` at ingest boundaries only.
- **No new dependencies** without a strong reason — current runtime deps are just `commander` and `js-yaml`.
- **`resolveRefs` is shallow** — resolves `$ref` at the parameter/requestBody level only. Does NOT recurse into schemas (avoids OOM on Stripe-scale specs).
- **Generated `_request` must treat non-2xx as rejection** — 3xx, 4xx, 5xx all reject with `Error("HTTP <status>: ...")`. Response stream errors also reject.
- **`filterEndpoints` applies tags AND include as intersection** — an endpoint must satisfy both filters when both are provided.
- **Tool names normalized via `normalizeToolName`**: camelCase → snake_case, version segments stripped (V1, V2).

## Testing Rules

- Every new library function gets at least one unit test.
- Integration tests spawn the compiled `dist/cli.js` via `spawnSync`.
- Smoke tests for generated MCP servers use the `bookApiSpec` helper in `cli.test.ts`.
- No mocking of internal modules — tests call real functions with fixture data.
- Test path-item parameter override (operation-level wins over path-level) explicitly.
