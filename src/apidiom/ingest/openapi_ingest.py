from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import yaml
from openapi_spec_validator import validate

from apidiom.models import (
    APIClientModel,
    APIEndpoint,
    APIParameter,
    APIResponse,
    AuthScheme,
    HTTPMethod,
    OpenAPISchema,
    ParameterLocation,
)

_HTTP_METHODS: set[HTTPMethod] = {
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "HEAD",
    "OPTIONS",
    "TRACE",
}


class OpenAPIIngestError(ValueError):
    """Raised when an OpenAPI document cannot be loaded or normalized."""


def load_openapi(source: str | Path) -> APIClientModel:
    source_label = str(source)
    raw_document = _read_source(source)
    document = _parse_document(raw_document, source_label)
    _validate_document(document, source_label)
    return _normalize_document(document, source_label)


def _read_source(source: str | Path) -> str:
    source_label = str(source)
    if _is_url(source_label):
        return _read_url(source_label)

    path = Path(source)
    if not path.exists():
        raise OpenAPIIngestError(
            f"OpenAPI file not found: {path}. Check the path and try again."
        )
    if not path.is_file():
        raise OpenAPIIngestError(
            f"OpenAPI source is not a file: {path}. Provide a JSON or YAML file."
        )
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OpenAPIIngestError(
            f"Could not read OpenAPI file: {path}. Check file permissions."
        ) from exc


def _read_url(url: str) -> str:
    try:
        with urlopen(url, timeout=30) as response:  # noqa: S310
            raw_body = cast(bytes, response.read())
            return raw_body.decode("utf-8")
    except HTTPError as exc:
        raise OpenAPIIngestError(
            f"Could not load OpenAPI URL: {url}. HTTP status {exc.code}."
        ) from exc
    except URLError as exc:
        raise OpenAPIIngestError(
            f"Could not load OpenAPI URL: {url}. Check the URL and network access."
        ) from exc
    except UnicodeDecodeError as exc:
        raise OpenAPIIngestError(
            f"Could not decode OpenAPI URL as UTF-8: {url}."
        ) from exc


def _parse_document(raw_document: str, source_label: str) -> dict[str, Any]:
    try:
        parsed = yaml.safe_load(raw_document)
    except yaml.YAMLError as exc:
        raise OpenAPIIngestError(
            f"Could not parse OpenAPI document: {source_label}. "
            "Provide valid JSON or YAML."
        ) from exc

    if not isinstance(parsed, dict):
        raise OpenAPIIngestError(
            f"Could not parse OpenAPI document: {source_label}. "
            "The top-level document must be an object."
        )
    return cast(dict[str, Any], parsed)


def _validate_document(document: dict[str, Any], source_label: str) -> None:
    try:
        validate(document)
    except Exception as exc:
        raise OpenAPIIngestError(
            f"OpenAPI validation failed for {source_label}. "
            f"Fix the spec and try again. Details: {exc}"
        ) from exc


def _normalize_document(document: dict[str, Any], source_label: str) -> APIClientModel:
    info = _as_mapping(document.get("info"))
    title = _as_string(info.get("title"), default="Untitled API")
    version = _as_string(info.get("version"), default="0.0.0")
    auth_schemes = _normalize_auth_schemes(document)
    endpoints = _normalize_endpoints(document)

    return APIClientModel(
        title=title,
        version=version,
        source=source_label,
        endpoints=endpoints,
        auth_schemes=auth_schemes,
    )


def _normalize_auth_schemes(document: dict[str, Any]) -> list[AuthScheme]:
    components = _as_mapping(document.get("components"))
    security_schemes = _as_mapping(components.get("securitySchemes"))
    auth_schemes: list[AuthScheme] = []

    for name, raw_scheme in security_schemes.items():
        scheme = _as_mapping(raw_scheme)
        auth_schemes.append(
            AuthScheme(
                name=name,
                type=_as_string(scheme.get("type"), default="unknown"),
                scheme=_optional_string(scheme.get("scheme")),
                bearer_format=_optional_string(scheme.get("bearerFormat")),
                api_key_name=_optional_string(scheme.get("name")),
                api_key_in=_optional_string(scheme.get("in")),
            )
        )

    return auth_schemes


def _normalize_endpoints(document: dict[str, Any]) -> list[APIEndpoint]:
    paths = _as_mapping(document.get("paths"))
    endpoints: list[APIEndpoint] = []

    for path, raw_path_item in paths.items():
        path_item = _as_mapping(raw_path_item)
        path_parameters = _normalize_parameters(path_item.get("parameters"))
        for method_name, raw_operation in path_item.items():
            method = method_name.upper()
            if method not in _HTTP_METHODS:
                continue
            operation = _as_mapping(raw_operation)
            operation_parameters = _normalize_parameters(operation.get("parameters"))
            parameters = _merge_parameters(path_parameters, operation_parameters)
            endpoints.append(
                APIEndpoint(
                    path=path,
                    method=method,
                    operation_id=_optional_string(operation.get("operationId")),
                    summary=_optional_string(operation.get("summary")),
                    path_parameters=[
                        parameter
                        for parameter in parameters
                        if parameter.location == "path"
                    ],
                    query_parameters=[
                        parameter
                        for parameter in parameters
                        if parameter.location == "query"
                    ],
                    request_schema=_normalize_request_schema(
                        operation.get("requestBody")
                    ),
                    response_schemas=_normalize_responses(operation.get("responses")),
                    auth_schemes=_normalize_operation_security(
                        operation.get("security")
                    ),
                )
            )

    return endpoints


def _normalize_parameters(raw_parameters: object) -> list[APIParameter]:
    if not isinstance(raw_parameters, list):
        return []

    parameters: list[APIParameter] = []
    for raw_parameter in raw_parameters:
        parameter = _as_mapping(raw_parameter)
        location = parameter.get("in")
        if location not in {"path", "query"}:
            continue
        schema = _as_mapping(parameter.get("schema"))
        parameters.append(
            APIParameter(
                name=_as_string(parameter.get("name"), default=""),
                location=cast(ParameterLocation, location),
                required=bool(parameter.get("required", location == "path")),
                description=_optional_string(parameter.get("description")),
                schema_model=OpenAPISchema(value=schema),
            )
        )

    return parameters


def _merge_parameters(
    path_parameters: list[APIParameter],
    operation_parameters: list[APIParameter],
) -> list[APIParameter]:
    merged = {
        (parameter.location, parameter.name): parameter for parameter in path_parameters
    }
    for parameter in operation_parameters:
        merged[(parameter.location, parameter.name)] = parameter
    return list(merged.values())


def _normalize_request_schema(raw_request_body: object) -> OpenAPISchema | None:
    request_body = _as_mapping(raw_request_body)
    content = _as_mapping(request_body.get("content"))
    schema = _first_json_schema(content)
    if schema is None:
        return None
    return OpenAPISchema(value=schema)


def _normalize_responses(raw_responses: object) -> list[APIResponse]:
    responses = _as_mapping(raw_responses)
    normalized: list[APIResponse] = []

    for status_code, raw_response in responses.items():
        response = _as_mapping(raw_response)
        content = _as_mapping(response.get("content"))
        schema = _first_json_schema(content)
        normalized.append(
            APIResponse(
                status_code=status_code,
                description=_optional_string(response.get("description")),
                schema_model=(
                    OpenAPISchema(value=schema) if schema is not None else None
                ),
            )
        )

    return normalized


def _normalize_operation_security(raw_security: object) -> list[str]:
    if not isinstance(raw_security, list):
        return []

    schemes: list[str] = []
    for requirement in raw_security:
        if isinstance(requirement, dict):
            schemes.extend(str(name) for name in requirement)
    return schemes


def _first_json_schema(content: dict[str, Any]) -> dict[str, Any] | None:
    media_type = content.get("application/json")
    if media_type is None and content:
        media_type = next(iter(content.values()))
    media_mapping = _as_mapping(media_type)
    schema = media_mapping.get("schema")
    if isinstance(schema, dict):
        return cast(dict[str, Any], schema)
    return None


def _is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def _as_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


def _as_string(value: object, *, default: str) -> str:
    if isinstance(value, str):
        return value
    return default


def _optional_string(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None
