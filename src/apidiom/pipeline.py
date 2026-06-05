from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast
from urllib.error import URLError
from urllib.request import urlopen

import yaml

from apidiom.config import GEMINI_PRIVACY_WARNING
from apidiom.generate.codegen import CodegenMode, generate_client_code
from apidiom.ingest.doc_to_spec import doc_to_spec
from apidiom.ingest.openapi_ingest import (
    OpenAPIIngestError,
    load_openapi,
    load_openapi_document,
    normalize_openapi_document,
)
from apidiom.llm.provider import LLMProvider
from apidiom.models import APIClientModel

InputKind = Literal["openapi", "unstructured"]
InputKindSource = Literal["detected", "explicit"]
Language = Literal["python"]


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


def _provider_warning(provider: LLMProvider | None) -> str | None:
    if provider is not None and provider.name == "gemini":
        return GEMINI_PRIVACY_WARNING
    return None


def _load_openapi_source(source: str | Path) -> tuple[dict[str, Any], APIClientModel]:
    try:
        if _is_existing_file_or_url(source):
            spec = load_openapi_document(source)
            model = load_openapi(source)
            return spec, model

        raw_document = str(source)
        inline_spec = _parse_mapping(raw_document)
        if inline_spec is None:
            raise OpenAPIIngestError(
                "Could not parse OpenAPI document: inline input. "
                "Provide valid JSON or YAML."
            )
        return inline_spec, normalize_openapi_document(inline_spec, "inline input")
    except OpenAPIIngestError as exc:
        raise RuntimeError(str(exc)) from exc


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
