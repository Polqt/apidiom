from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from apidiom.ingest.doc_to_spec import collect_unverified_items
from apidiom.models import APIClientModel, APIEndpoint, APIParameter

CodegenMode = Literal["auto", "openapi-generator", "builtin"]
CodegenTier = Literal["openapi-generator", "builtin"]

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
_LOGGER = logging.getLogger(__name__)


class SubprocessRunner(Protocol):
    def __call__(
        self,
        cmd: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]: ...


class CodegenError(RuntimeError):
    pass


@dataclass(frozen=True)
class CodegenResult:
    tier: CodegenTier
    client_text: str
    files: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _TemplateParameter:
    name: str
    safe_name: str
    required: bool


@dataclass(frozen=True)
class _TemplateEndpoint:
    function_name: str
    method: str
    path_expression: str
    parameters: list[_TemplateParameter]
    query_parameters: list[_TemplateParameter]
    has_body: bool
    unverified_comments: list[str]


def choose_codegen_tier(
    *,
    mode: CodegenMode,
    has_openapi_generator: Callable[[], bool] | None = None,
    has_java: Callable[[], bool] | None = None,
) -> CodegenTier:
    cli_available = has_openapi_generator or has_openapi_generator_cli
    java_available = has_java or has_working_java
    if mode == "builtin":
        return "builtin"
    if mode == "openapi-generator":
        if cli_available() and java_available():
            return "openapi-generator"
        raise CodegenError(
            "openapi-generator was requested but is unavailable. "
            "Install Java and openapi-generator-cli, or use --codegen builtin."
        )
    if cli_available() and java_available():
        return "openapi-generator"
    return "builtin"


def generate_client_code(
    spec: dict[str, Any],
    model: APIClientModel,
    *,
    mode: CodegenMode = "auto",
    output_dir: Path | None = None,
    runner: SubprocessRunner | None = None,
    has_openapi_generator: Callable[[], bool] | None = None,
    has_java: Callable[[], bool] | None = None,
    model_generator: Callable[[str], str] | None = None,
) -> CodegenResult:
    tier = choose_codegen_tier(
        mode=mode,
        has_openapi_generator=has_openapi_generator,
        has_java=has_java,
    )
    _LOGGER.info("Using %s codegen tier", tier)
    if tier == "openapi-generator":
        return _run_openapi_generator(
            spec,
            runner=runner or _run_subprocess,
            output_dir=output_dir,
        )
    return _run_builtin_fallback(spec, model, model_generator=model_generator)


def has_openapi_generator_cli() -> bool:
    return shutil.which("openapi-generator-cli") is not None


def has_working_java() -> bool:
    if shutil.which("java") is None:
        return False
    result = subprocess.run(
        ["java", "-version"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _run_openapi_generator(
    spec: dict[str, Any],
    *,
    runner: SubprocessRunner,
    output_dir: Path | None,
) -> CodegenResult:
    target_dir = output_dir or Path(tempfile.mkdtemp(prefix="apidiom-openapi-client-"))
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as spec_file:
            json.dump(spec, spec_file)
            spec_path = Path(spec_file.name)

        result = runner(
            [
                "openapi-generator-cli",
                "generate",
                "-g",
                "python",
                "--library",
                "httpx",
                "-i",
                str(spec_path),
                "-o",
                str(target_dir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        if "spec_path" in locals():
            spec_path.unlink(missing_ok=True)

    if result.returncode != 0:
        shutil.rmtree(target_dir, ignore_errors=True)
        message = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise CodegenError(f"openapi-generator-cli failed: {message}")

    files = _read_generated_files(target_dir)
    client_text = _prepend_unverified_header(_join_files(files), spec)
    return CodegenResult(
        tier="openapi-generator",
        client_text=client_text,
        files=files,
    )


def _run_builtin_fallback(
    spec: dict[str, Any],
    model: APIClientModel,
    *,
    model_generator: Callable[[str], str] | None,
) -> CodegenResult:
    spec_json = json.dumps(spec, indent=2, sort_keys=True)
    models_code = (
        model_generator(spec_json)
        if model_generator is not None
        else _generate_models_with_datamodel_codegen(spec_json)
    )
    template = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    ).get_template("httpx_client.py.j2")
    client_text = template.render(
        models_code=models_code.strip(),
        endpoints=[_template_endpoint(endpoint, spec) for endpoint in model.endpoints],
        unverified_comments=_unverified_comments(spec),
    )
    return CodegenResult(
        tier="builtin",
        client_text=client_text,
        files={"client.py": client_text},
    )


def _generate_models_with_datamodel_codegen(spec_json: str) -> str:
    if shutil.which("datamodel-codegen") is None:
        raise CodegenError(
            "Built-in codegen dependencies are not installed. "
            "Run: pip install apidiom[codegen]"
        )
    with tempfile.TemporaryDirectory(prefix="apidiom-datamodel-") as temp_dir:
        input_path = Path(temp_dir) / "schemas.json"
        output_path = Path(temp_dir) / "models.py"
        input_path.write_text(_schema_document(spec_json), encoding="utf-8")
        result = subprocess.run(
            [
                "datamodel-codegen",
                "--input",
                str(input_path),
                "--input-file-type",
                "jsonschema",
                "--output",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise CodegenError(f"datamodel-code-generator failed: {message}")
        return output_path.read_text(encoding="utf-8")


def _schema_document(spec_json: str) -> str:
    spec = json.loads(spec_json)
    schemas = spec.get("components", {}).get("schemas", {})
    return json.dumps(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "ApidiomModels",
            "type": "object",
            "definitions": schemas,
        }
    )


def _read_generated_files(output_dir: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            files[path.relative_to(output_dir).as_posix()] = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
    return files


def _join_files(files: dict[str, str]) -> str:
    return "\n\n".join(
        f"# --- {path} ---\n{content}" for path, content in files.items()
    )


def _prepend_unverified_header(client_text: str, spec: dict[str, Any]) -> str:
    comments = _unverified_comments(spec)
    if not comments:
        return client_text
    block = "\n".join(comments)
    return f'"""Unverified API documentation notes:\n{block}\n"""\n\n{client_text}'


def _template_endpoint(
    endpoint: APIEndpoint,
    spec: dict[str, Any],
) -> _TemplateEndpoint:
    path_parameters = [
        _template_parameter(parameter) for parameter in endpoint.path_parameters
    ]
    query_parameters = [
        _template_parameter(parameter) for parameter in endpoint.query_parameters
    ]
    return _TemplateEndpoint(
        function_name=_function_name(endpoint),
        method=endpoint.method,
        path_expression=_path_expression(endpoint.path),
        parameters=path_parameters + query_parameters,
        query_parameters=query_parameters,
        has_body=endpoint.request_schema is not None,
        unverified_comments=_endpoint_unverified_comments(endpoint, spec),
    )


def _template_parameter(parameter: APIParameter) -> _TemplateParameter:
    return _TemplateParameter(
        name=parameter.name,
        safe_name=_safe_identifier(parameter.name),
        required=parameter.required,
    )


def _function_name(endpoint: APIEndpoint) -> str:
    if endpoint.operation_id:
        return _safe_identifier(_camel_to_snake(endpoint.operation_id))
    method = endpoint.method.lower()
    path_name = "_".join(part.strip("{}") for part in endpoint.path.split("/") if part)
    return _safe_identifier(f"{method}_{path_name}")


def _path_expression(path: str) -> str:
    if "{" not in path:
        return json.dumps(path)
    expression = re.sub(r"{([^}]+)}", r"{\1}", path)
    return f'f"{expression}"'


def _unverified_comments(spec: dict[str, Any]) -> list[str]:
    comments: list[str] = []
    for item in collect_unverified_items(spec):
        if ": " in item:
            _, value = item.split(": ", 1)
        else:
            value = item
        if value.startswith("UNVERIFIED:"):
            comments.append(f"# UNVERIFIED: {value}")
        else:
            comments.append(f"# UNVERIFIED: {value} not specified in docs")
    return _dedupe(comments)


def _endpoint_unverified_comments(
    endpoint: APIEndpoint,
    spec: dict[str, Any],
) -> list[str]:
    operation = _operation_for_endpoint(endpoint, spec)
    if operation is None:
        return []
    return _unverified_comments(operation)


def _operation_for_endpoint(
    endpoint: APIEndpoint,
    spec: dict[str, Any],
) -> dict[str, Any] | None:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return None
    path_item = paths.get(endpoint.path)
    if not isinstance(path_item, dict):
        return None
    operation = path_item.get(endpoint.method.lower())
    if isinstance(operation, dict):
        return cast(dict[str, Any], operation)
    return None


def _safe_identifier(value: str) -> str:
    normalized = re.sub(r"\W+", "_", value).strip("_").lower()
    if not normalized:
        return "value"
    if normalized[0].isdigit():
        return f"value_{normalized}"
    if normalized in {"from", "class", "pass", "None", "True", "False"}:
        return f"{normalized}_"
    return normalized


def _camel_to_snake(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _run_subprocess(
    cmd: list[str],
    *,
    capture_output: bool,
    text: bool,
    check: bool,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=capture_output,
        text=text,
        check=check,
    )
