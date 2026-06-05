from pathlib import Path
from tempfile import NamedTemporaryFile, gettempdir
from typing import Annotated, Any, cast

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from apidiom import pipeline
from apidiom.config import GEMINI_PRIVACY_WARNING
from apidiom.generate.codegen import CodegenMode
from apidiom.llm.provider import get_provider
from apidiom.pipeline import InputKind, Language, PipelineResult

_WEB_DIR = Path(__file__).parent
_PROVIDERS = ("null", "gemini", "ollama")
_CODEGEN_MODES = ("auto", "openapi-generator", "builtin")
_INPUT_KINDS = ("openapi", "unstructured")

app = FastAPI(title="apidiom")
app.mount("/static", StaticFiles(directory=_WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=_WEB_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Response:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "providers": _PROVIDERS,
            "codegen_modes": _CODEGEN_MODES,
            "input_kinds": _INPUT_KINDS,
            "gemini_warning": GEMINI_PRIVACY_WARNING,
        },
    )


@app.post("/generate")
async def generate(
    request: Request,
    source_url: Annotated[str, Form()] = "",
    source_file: Annotated[UploadFile | None, File()] = None,
    provider: Annotated[str, Form()] = "null",
    lang: Annotated[str, Form()] = "python",
    codegen: Annotated[str, Form()] = "auto",
    input_kind: Annotated[str, Form()] = "openapi",
    format: str | None = None,
) -> Response:
    wants_json = _wants_json(request, format)
    source: str | Path | None = None
    try:
        source = await _read_source(
            source_url,
            source_file,
            cast(InputKind, input_kind),
        )
        result = _run_pipeline(
            source,
            provider=provider,
            lang=cast(Language, lang),
            codegen=cast(CodegenMode, codegen),
            input_kind=cast(InputKind, input_kind),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return _error_response(str(exc), wants_json)
    finally:
        if isinstance(source, Path) and source.parent == Path(gettempdir()):
            source.unlink(missing_ok=True)

    if wants_json:
        return JSONResponse(_result_payload(result))
    return templates.TemplateResponse(
        request,
        "result.html",
        _result_context(result),
    )


def _run_pipeline(
    source: str | Path,
    *,
    provider: str,
    lang: Language,
    codegen: CodegenMode,
    input_kind: InputKind,
) -> PipelineResult:
    return pipeline.generate_client(
        source,
        provider=get_provider(provider),
        lang=lang,
        codegen=codegen,
        input_kind=input_kind,
    )


async def _read_source(
    source_url: str,
    source_file: UploadFile | None,
    input_kind: InputKind,
) -> str | Path:
    trimmed_url = source_url.strip()
    has_file = source_file is not None and bool(source_file.filename)
    if bool(trimmed_url) == has_file:
        raise ValueError("Provide exactly one input: a URL/path or an uploaded file.")
    if trimmed_url:
        return trimmed_url
    if source_file is None:
        raise ValueError("Provide exactly one input: a URL/path or an uploaded file.")

    uploaded = await source_file.read()
    text = uploaded.decode("utf-8")
    if input_kind == "unstructured":
        return text

    suffix = Path(source_file.filename or "openapi.yaml").suffix or ".yaml"
    with NamedTemporaryFile("w", encoding="utf-8", suffix=suffix, delete=False) as file:
        file.write(text)
        return Path(file.name)


def _wants_json(request: Request, format: str | None) -> bool:
    if format == "json":
        return True
    return "application/json" in request.headers.get("accept", "")


def _result_payload(result: PipelineResult) -> dict[str, Any]:
    return {
        "code": result.generated_client or _files_to_text(result.generated_files),
        "unknowns": result.unverified_items,
        "tier": result.codegen_tier,
        "notes": result.notes,
    }


def _result_context(result: PipelineResult) -> dict[str, Any]:
    unknown_count = len(result.unverified_items)
    noun = "field" if unknown_count == 1 else "fields"
    return {
        "code": result.generated_client or _files_to_text(result.generated_files),
        "tier": result.codegen_tier,
        "unknowns": result.unverified_items,
        "unknown_count": unknown_count,
        "unknown_noun": noun,
        "notes": result.notes,
        "provider_warning": result.provider_warning,
    }


def _files_to_text(files: dict[str, str]) -> str:
    if not files:
        return ""
    parts: list[str] = []
    for path, content in sorted(files.items()):
        parts.append(f"# {path}\n{content}")
    return "\n\n".join(parts)


def _error_response(message: str, wants_json: bool) -> Response:
    if wants_json:
        return JSONResponse({"error": message}, status_code=400)
    return HTMLResponse(
        '<section class="result-panel error" role="alert">'
        "<h2>Generation failed</h2>"
        f"<p>{_escape(message)}</p>"
        "</section>"
    )


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
