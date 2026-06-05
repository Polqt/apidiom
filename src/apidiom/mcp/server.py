from pathlib import Path
from typing import Literal, TypedDict

from mcp.server.fastmcp import FastMCP

from apidiom import pipeline
from apidiom.config import GEMINI_PRIVACY_WARNING
from apidiom.generate.codegen import CodegenMode
from apidiom.llm.provider import get_provider
from apidiom.pipeline import InputKind, Language, PipelineResult

ProviderName = Literal["null", "gemini", "ollama"]


class MCPToolError(RuntimeError):
    """Clean user-facing MCP tool error."""


class GenerateClientResponse(TypedDict):
    code: str
    tier: str | None
    unverified_fields: list[str]
    notes: list[str]
    privacy_warning: str | None
    input_kind: str | None
    input_kind_source: str | None
    message: str


mcp = FastMCP("apidiom")


@mcp.tool()
def generate_client(
    source: str,
    provider: ProviderName = "null",
    lang: Language = "python",
    codegen: CodegenMode = "auto",
    input_kind: InputKind | None = None,
) -> GenerateClientResponse:
    try:
        selected_provider = get_provider(provider)
        result = pipeline.generate_client(
            source,
            provider=selected_provider,
            lang=lang,
            codegen=codegen,
            input_kind=input_kind,
        )
    except Exception as exc:
        raise MCPToolError(str(exc)) from None

    return _response(result, provider=provider)


def _response(
    result: PipelineResult,
    *,
    provider: ProviderName,
) -> GenerateClientResponse:
    warning = result.provider_warning
    if provider == "gemini" and not warning:
        warning = GEMINI_PRIVACY_WARNING
    message = "Client generated."
    if warning:
        message = f"{warning} Client generated."
    return {
        "code": result.generated_client or _files_to_text(result.generated_files),
        "tier": result.codegen_tier,
        "unverified_fields": list(result.unverified_items),
        "notes": list(result.notes),
        "privacy_warning": warning,
        "input_kind": result.input_kind,
        "input_kind_source": result.input_kind_source,
        "message": message,
    }


def _files_to_text(files: dict[str, str]) -> str:
    if not files:
        return ""
    return "\n\n".join(
        f"# {Path(path).as_posix()}\n{content}"
        for path, content in sorted(files.items())
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
