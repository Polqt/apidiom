from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from apidiom.config import GEMINI_PRIVACY_WARNING
from apidiom.generate.codegen import CodegenMode, generate_client_code
from apidiom.ingest.doc_to_spec import doc_to_spec
from apidiom.ingest.openapi_ingest import load_openapi, load_openapi_document
from apidiom.llm.provider import LLMProvider
from apidiom.models import APIClientModel

InputKind = Literal["openapi", "unstructured"]
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


def generate_client(
    source: str | Path,
    *,
    provider: LLMProvider | None = None,
    lang: Language = "python",
    input_kind: InputKind = "openapi",
    codegen: CodegenMode = "auto",
    model_generator: Callable[[str], str] | None = None,
) -> PipelineResult:
    if lang != "python":
        raise RuntimeError("Only Python client generation is supported in the MVP.")
    provider_warning = _provider_warning(provider)
    if input_kind == "unstructured":
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
        )

    spec = load_openapi_document(source)
    model = load_openapi(source)
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
    )


def _provider_warning(provider: LLMProvider | None) -> str | None:
    if provider is not None and provider.name == "gemini":
        return GEMINI_PRIVACY_WARNING
    return None
