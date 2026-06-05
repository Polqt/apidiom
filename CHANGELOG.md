# Changelog

All notable changes to this project will be documented in this file.

## v0.1.0 - 2026-06-05

Initial MVP release.

- Adds a Python CLI, `apidiom`, for generating Python `httpx` clients from API
  documentation.
- Supports validated OpenAPI JSON/YAML input from files or URLs.
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
- Includes a stateless FastAPI web UI and JSON endpoint over the same pipeline
  used by the CLI.
- Adds a separate Astro/Starlight documentation site under `docs/`.
