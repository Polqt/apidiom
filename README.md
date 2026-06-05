# apidiom

`apidiom` turns API documentation into idiomatic Python API clients.

The wedge: it can generate clients from messy docs that do not have a clean
OpenAPI spec, not just from already-valid OpenAPI documents. Unstructured docs
are extracted into a validated OpenAPI spec first, then client generation is
delegated to existing tools.

## Install

After v0.1.0 is published to PyPI:

```bash
python -m pip install apidiom
```

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

For the primary codegen path, install Java and `openapi-generator-cli`.
If Java is not available, `apidiom` can use its no-Java fallback:
`datamodel-code-generator` for pydantic models plus a minimal httpx wrapper
template.

## Quickstart

Generate from an existing OpenAPI spec:

```bash
apidiom generate ./openapi.yaml --output client.py --codegen builtin
```

Generate from messy documentation:

```bash
apidiom generate ./docs-page.html \
  --input-kind unstructured \
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
