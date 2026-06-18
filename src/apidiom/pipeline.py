from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast
from urllib.error import URLError
from urllib.request import urlopen

import yaml

from apidiom.config import GEMINI_PRIVACY_WARNING
from apidiom.generate import langchain_gen, schema_gen
from apidiom.generate import mcp as mcp_codegen
from apidiom.generate.codegen import CodegenMode, generate_client_code
from apidiom.generate.endpoint_utils import default_base_url
from apidiom.generate.enrichment import enrich_description
from apidiom.ingest.discovery import discover_openapi_spec
from apidiom.ingest.doc_to_spec import doc_to_spec
from apidiom.ingest.merge import merge_models
from apidiom.ingest.openapi_ingest import (
    OpenAPIIngestError,
    load_openapi,
    load_openapi_document,
    normalize_openapi_document,
)
from apidiom.llm.provider import LLMProvider
from apidiom.models import APIClientModel, APIEndpoint

InputKind = Literal["openapi", "unstructured"]
InputKindSource = Literal["detected", "explicit"]
Language = Literal["python"]
OpenAPISource = str | Path
OpenAPISources = OpenAPISource | Sequence[OpenAPISource]
AgentToolTarget = Literal["mcp", "langchain", "schema"]


@dataclass(frozen=True)
class PipelineResult:
    spec: dict[str, Any]
    model: APIClientModel
    generated_client: str | None = None
    generated_files: dict[str, str] = field(default_factory=dict)
    codegen_tier: str | None = None
    unverified_items: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    provider_warning: str | None = None
    input_kind: InputKind | None = None
    input_kind_source: InputKindSource | None = None


@dataclass(frozen=True)
class ToolGenerationRequest:
    target: AgentToolTarget
    sources: OpenAPISources
    include_tags: list[str] = field(default_factory=list)
    include_operations: list[str] = field(default_factory=list)
    provider: LLMProvider | None = None
    enrich_docs: bool = False
    schema_format: schema_gen.SchemaFormat = "anthropic"


def detect_input_kind(source: str | Path) -> InputKind:
    """Conservatively detect OpenAPI only when the source is clearly a spec."""
    raw_source = _read_source_for_detection(source)
    if raw_source is None:
        return "unstructured"

    document = _parse_mapping(raw_source)
    if document is None:
        return "unstructured"
    if _is_openapi_document_shape(document):
        return "openapi"
    return "unstructured"


def generate_client(
    source: str | Path,
    *,
    provider: LLMProvider | None = None,
    lang: Language = "python",
    input_kind: InputKind | None = None,
    codegen: CodegenMode = "auto",
    model_generator: Callable[[str], str] | None = None,
) -> PipelineResult:
    if lang != "python":
        raise RuntimeError("Only Python client generation is supported in the MVP.")
    provider_warning = _provider_warning(provider)
    resolved_input_kind = input_kind or detect_input_kind(source)
    input_kind_source: InputKindSource = (
        "detected" if input_kind is None else "explicit"
    )

    if resolved_input_kind == "unstructured":
        if provider is None:
            raise RuntimeError(
                "Unstructured documentation needs an LLM provider. "
                "Use --provider gemini or --provider ollama."
            )
        doc_result = doc_to_spec(str(source), provider=provider)
        codegen_result = generate_client_code(
            doc_result.spec,
            doc_result.model,
            mode=codegen,
            model_generator=model_generator,
        )
        return PipelineResult(
            spec=doc_result.spec,
            model=doc_result.model,
            generated_client=codegen_result.client_text,
            generated_files=codegen_result.files,
            codegen_tier=codegen_result.tier,
            unverified_items=doc_result.unverified_items,
            notes=doc_result.notes,
            provider_warning=provider_warning,
            input_kind=resolved_input_kind,
            input_kind_source=input_kind_source,
        )

    spec, model = _load_openapi_source(source)
    codegen_result = generate_client_code(
        spec,
        model,
        mode=codegen,
        model_generator=model_generator,
    )
    return PipelineResult(
        spec=spec,
        model=model,
        generated_client=codegen_result.client_text,
        generated_files=codegen_result.files,
        codegen_tier=codegen_result.tier,
        provider_warning=provider_warning,
        input_kind=resolved_input_kind,
        input_kind_source=input_kind_source,
    )


def generate_mcp_server(
    source: OpenAPISources,
    *,
    include_tags: list[str] | None = None,
    include_operations: list[str] | None = None,
    provider: LLMProvider | None = None,
    enrich_docs: bool = False,
) -> PipelineResult:
    return generate_agent_tools(
        ToolGenerationRequest(
            target="mcp",
            sources=source,
            include_tags=include_tags or [],
            include_operations=include_operations or [],
            provider=provider,
            enrich_docs=enrich_docs,
        )
    )


def generate_agent_tools(request: ToolGenerationRequest) -> PipelineResult:
    spec, model = _load_openapi_sources(request.sources, validate_document=False)
    enricher = _description_enricher(request.provider) if request.enrich_docs else None
    if request.target == "mcp":
        return _generate_mcp_result(spec, model, request, enricher=enricher)
    if request.target == "langchain":
        return _generate_langchain_result(spec, model, request, enricher=enricher)
    return _generate_schema_result(spec, model, request, enricher=enricher)


def _generate_mcp_result(
    spec: dict[str, Any],
    model: APIClientModel,
    request: ToolGenerationRequest,
    *,
    enricher: Callable[[APIEndpoint], str] | None,
) -> PipelineResult:
    server_text = mcp_codegen.generate_mcp_server(
        spec,
        model,
        include_tags=request.include_tags,
        include_operations=request.include_operations,
        enricher=enricher,
    )
    readme_text = _mcp_readme(
        source=_source_label(request.sources),
        server_name="<generated-server-file>",
        server_text=server_text,
        operations=mcp_codegen.list_mcp_operations(
            spec,
            model,
            include_tags=request.include_tags,
            include_operations=request.include_operations,
        ),
    )
    return PipelineResult(
        spec=spec,
        model=model,
        generated_client=server_text,
        generated_files={"server.py": server_text, "README.md": readme_text},
        codegen_tier="mcp",
        input_kind="openapi",
        input_kind_source="explicit",
    )


def list_mcp_operations(
    source: OpenAPISources,
    *,
    include_tags: list[str] | None = None,
    include_operations: list[str] | None = None,
) -> list[mcp_codegen.MCPOperationSummary]:
    spec, model = _load_openapi_sources(source, validate_document=False)
    return mcp_codegen.list_mcp_operations(
        spec,
        model,
        include_tags=include_tags,
        include_operations=include_operations,
    )


def generate_langchain_tools(
    source: OpenAPISources,
    *,
    include_tags: list[str] | None = None,
    include_operations: list[str] | None = None,
    provider: LLMProvider | None = None,
    enrich_docs: bool = False,
) -> PipelineResult:
    return generate_agent_tools(
        ToolGenerationRequest(
            target="langchain",
            sources=source,
            include_tags=include_tags or [],
            include_operations=include_operations or [],
            provider=provider,
            enrich_docs=enrich_docs,
        )
    )


def _generate_langchain_result(
    spec: dict[str, Any],
    model: APIClientModel,
    request: ToolGenerationRequest,
    *,
    enricher: Callable[[APIEndpoint], str] | None,
) -> PipelineResult:
    tools_text = langchain_gen.generate_langchain_tools(
        spec,
        model,
        include_tags=request.include_tags,
        include_operations=request.include_operations,
        enricher=enricher,
    )
    return PipelineResult(
        spec=spec,
        model=model,
        generated_client=tools_text,
        generated_files={"tools.py": tools_text},
        codegen_tier="langchain",
        input_kind="openapi",
        input_kind_source="explicit",
    )


def generate_tool_schema(
    source: OpenAPISources,
    *,
    schema_format: schema_gen.SchemaFormat = "anthropic",
    include_tags: list[str] | None = None,
    include_operations: list[str] | None = None,
    provider: LLMProvider | None = None,
    enrich_docs: bool = False,
) -> PipelineResult:
    return generate_agent_tools(
        ToolGenerationRequest(
            target="schema",
            sources=source,
            include_tags=include_tags or [],
            include_operations=include_operations or [],
            provider=provider,
            enrich_docs=enrich_docs,
            schema_format=schema_format,
        )
    )


def _generate_schema_result(
    spec: dict[str, Any],
    model: APIClientModel,
    request: ToolGenerationRequest,
    *,
    enricher: Callable[[APIEndpoint], str] | None,
) -> PipelineResult:
    schema_text = schema_gen.generate_tool_schema(
        spec,
        model,
        schema_format=request.schema_format,
        include_tags=request.include_tags,
        include_operations=request.include_operations,
        enricher=enricher,
    )
    return PipelineResult(
        spec=spec,
        model=model,
        generated_client=schema_text,
        generated_files={"tools.json": schema_text},
        codegen_tier=f"schema:{request.schema_format}",
        input_kind="openapi",
        input_kind_source="explicit",
    )


def _provider_warning(provider: LLMProvider | None) -> str | None:
    if provider is not None and provider.name == "gemini":
        return GEMINI_PRIVACY_WARNING
    return None


def _description_enricher(
    provider: LLMProvider | None,
) -> Callable[[APIEndpoint], str]:
    if provider is None:
        raise RuntimeError("--enrich-docs needs an LLM provider.")

    def enrich(endpoint: APIEndpoint) -> str:
        return enrich_description(endpoint, provider)

    return enrich


def _mcp_readme(
    *,
    source: str,
    server_name: str,
    server_text: str,
    operations: list[mcp_codegen.MCPOperationSummary],
) -> str:
    check = mcp_codegen.validate_mcp_server_text(server_text)
    env_vars = "\n".join(f"- `{env_var}`" for env_var in check.env_vars)
    selectors = "\n".join(
        f"- `{operation.selector}` -> `{operation.function_name}`"
        for operation in operations
    )
    return f"""# Generated MCP server

Source: `{source}`

Run:

```bash
python {server_name}
```

Environment variables:

{env_vars or "- None"}

Exported tools:

{selectors or "- None"}
"""


def _load_openapi_source(
    source: str | Path,
    *,
    validate_document: bool = True,
) -> tuple[dict[str, Any], APIClientModel]:
    try:
        resolved_source = _discover_source(source)
        if _is_existing_file_or_url(resolved_source):
            spec = load_openapi_document(
                resolved_source,
                validate_document=validate_document,
            )
            _annotate_spec_base_urls(spec)
            model = load_openapi(resolved_source, validate_document=validate_document)
            return spec, model

        raw_document = str(resolved_source)
        inline_spec = _parse_mapping(raw_document)
        if inline_spec is None:
            raise OpenAPIIngestError(
                "Could not parse OpenAPI document: inline input. "
                "Provide valid JSON or YAML."
            )
        _annotate_spec_base_urls(inline_spec)
        return inline_spec, normalize_openapi_document(
            inline_spec,
            "inline input",
            validate_document=validate_document,
        )
    except OpenAPIIngestError as exc:
        raise RuntimeError(str(exc)) from exc


def _load_openapi_sources(
    source: OpenAPISources,
    *,
    validate_document: bool = True,
) -> tuple[dict[str, Any], APIClientModel]:
    sources = (
        list(source)
        if isinstance(source, Sequence) and not isinstance(source, str)
        else [source]
    )
    loaded = [
        _load_openapi_source(item, validate_document=validate_document)
        for item in sources
    ]
    if len(loaded) == 1:
        return loaded[0]
    specs = [spec for spec, _model in loaded]
    models = [model for _spec, model in loaded]
    return _merge_specs(specs), merge_models(models)


def _merge_specs(specs: list[dict[str, Any]]) -> dict[str, Any]:
    if not specs:
        return {}
    merged: dict[str, Any] = {
        "openapi": specs[0].get("openapi", "3.1.0"),
        "info": {"title": "merged", "version": "0.0.0"},
        "servers": specs[0].get("servers", []),
        "paths": {},
        "components": {"securitySchemes": {}},
    }
    paths = cast(dict[str, Any], merged["paths"])
    security_schemes = cast(
        dict[str, Any],
        cast(dict[str, Any], merged["components"])["securitySchemes"],
    )
    for spec in specs:
        raw_paths = spec.get("paths")
        if isinstance(raw_paths, dict):
            for path, path_item in raw_paths.items():
                paths.setdefault(str(path), path_item)
        components = spec.get("components")
        if isinstance(components, dict):
            raw_security = components.get("securitySchemes")
            if isinstance(raw_security, dict):
                for name, scheme in raw_security.items():
                    security_schemes.setdefault(str(name), scheme)
    return merged


def _annotate_spec_base_urls(spec: dict[str, Any]) -> None:
    base_url = default_base_url(spec)
    if not base_url:
        return
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if isinstance(operation, dict):
                operation.setdefault("x-apidiom-base-url", base_url)


def _source_label(source: OpenAPISources) -> str:
    if isinstance(source, Sequence) and not isinstance(source, str):
        return ", ".join(str(item) for item in source)
    return str(source)


def _discover_source(source: OpenAPISource) -> OpenAPISource:
    source_label = str(source)
    if not _should_discover(source_label):
        return source
    discovered = discover_openapi_spec(source_label)
    return discovered or source


def _read_source_for_detection(source: str | Path) -> str | None:
    source_label = str(source)
    if _is_url(source_label):
        try:
            with urlopen(source_label, timeout=30) as response:  # noqa: S310
                raw_body = cast(bytes, response.read())
                return raw_body.decode("utf-8")
        except (OSError, UnicodeDecodeError, URLError):
            return None

    path = Path(source)
    if path.exists() and path.is_file():
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None
    if isinstance(source, Path):
        return None
    return source_label


def _parse_mapping(raw_document: str) -> dict[str, Any] | None:
    try:
        parsed = yaml.safe_load(raw_document)
    except yaml.YAMLError:
        return None
    if not isinstance(parsed, dict):
        return None
    return cast(dict[str, Any], parsed)


def _is_openapi_document_shape(document: dict[str, Any]) -> bool:
    if isinstance(document.get("openapi"), str) or isinstance(
        document.get("swagger"),
        str,
    ):
        return True
    return isinstance(document.get("info"), dict) and isinstance(
        document.get("paths"),
        dict,
    )


def _is_existing_file_or_url(source: str | Path) -> bool:
    return _is_url(str(source)) or Path(source).exists()


def _is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def _should_discover(source: str) -> bool:
    if not _is_url(source):
        return False
    lowered = source.lower().rstrip("/")
    return not lowered.endswith(
        (
            ".json",
            ".yaml",
            ".yml",
            "/openapi.json",
            "/openapi.yaml",
            "/swagger.json",
            "/swagger.yaml",
        )
    )
