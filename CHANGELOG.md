# Changelog

All notable changes to this project will be documented in this file.

## v0.1.0 - 2026-06-07

Initial MVP release: generate type-safe Python clients from messy API
documentation that has no OpenAPI spec, not only from clean specs.

- Adds conservative auto-detection for clean OpenAPI input versus unstructured
  documentation, with explicit overrides available in every front-end.
- Supports validated OpenAPI JSON/YAML input from files, URLs, or inline text.
- Adds unstructured documentation extraction through pluggable LLM providers:
  `null`, `gemini`, and local/offline `ollama`.
- Validates extracted OpenAPI and attempts bounded repair while preserving the
  documented endpoint set.
- Delegates primary Python client generation to `openapi-generator-cli` when
  Java and the CLI are available.
- Provides a no-Java fallback using `datamodel-code-generator` plus a minimal
  `httpx` wrapper template.
- Carries uncertain fields forward as `x-apidiom-unknown`, `UNVERIFIED` notes,
  CLI summaries, web warnings, and generated-code comments.
- Includes a CLI, stateless FastAPI web UI/JSON endpoint, and MCP server over
  the same shared generation pipeline.
- Adds a separate Astro/Starlight documentation site under `docs/`.
