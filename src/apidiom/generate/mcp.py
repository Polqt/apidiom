from __future__ import annotations

import json
import keyword
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from apidiom.generate.codegen import _camel_to_snake, _function_name, _safe_identifier
from apidiom.models import APIClientModel, APIEndpoint, APIParameter, AuthScheme

_TEMPLATE_DIR = Path(__file__).parent / "templates"


@dataclass(frozen=True)
class _MCPParameter:
    name: str
    safe_name: str
    annotation: str
    required: bool


@dataclass(frozen=True)
class _MCPAuthHeader:
    header_name: str
    env_var: str
    value_expression: str


@dataclass(frozen=True)
class _MCPEndpoint:
    function_name: str
    method: str
    path_expression: str
    description: str
    body_hint: str | None
    parameters: list[_MCPParameter]
    query_parameters: list[_MCPParameter]
    has_body: bool
    auth_headers: list[_MCPAuthHeader]


def generate_mcp_server(
    spec: dict[str, Any],
    model: APIClientModel,
    *,
    include_tags: list[str] | None = None,
    include_operations: list[str] | None = None,
) -> str:
    """Generate a runnable Python MCP server for an OpenAPI model."""
    endpoints = [
        endpoint
        for endpoint in model.endpoints
        if _include_endpoint(
            endpoint,
            spec,
            include_tags=include_tags or [],
            include_operations=include_operations or [],
        )
    ]
    if not endpoints:
        raise ValueError("No OpenAPI endpoints matched MCP filters.")
    template = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    ).get_template("mcp_server.py.j2")
    server_text = template.render(
        server_name=_safe_identifier(model.title),
        default_base_url=_default_base_url(spec),
        endpoints=[_template_endpoint(endpoint, model) for endpoint in endpoints],
    )
    return f"{server_text.rstrip()}\n"


def _template_endpoint(endpoint: APIEndpoint, model: APIClientModel) -> _MCPEndpoint:
    path_parameters = [
        _template_parameter(parameter) for parameter in endpoint.path_parameters
    ]
    query_parameters = [
        _template_parameter(parameter) for parameter in endpoint.query_parameters
    ]
    all_parameters = (
        path_parameters
        + [parameter for parameter in query_parameters if parameter.required]
        + [parameter for parameter in query_parameters if not parameter.required]
    )
    return _MCPEndpoint(
        function_name=_function_name(endpoint),
        method=endpoint.method,
        path_expression=_path_expression(endpoint.path, path_parameters),
        description=_description(endpoint),
        body_hint=_body_hint(endpoint),
        parameters=all_parameters,
        query_parameters=query_parameters,
        has_body=endpoint.request_schema is not None,
        auth_headers=_auth_headers(endpoint, model.auth_schemes),
    )


def _template_parameter(parameter: APIParameter) -> _MCPParameter:
    annotation = _python_type(parameter.schema_model.value)
    return _MCPParameter(
        name=parameter.name,
        safe_name=_safe_parameter_name(parameter.name),
        annotation=annotation,
        required=parameter.required,
    )


def _python_type(schema: dict[str, Any]) -> str:
    schema_type = schema.get("type")
    if schema_type == "integer":
        return "int"
    if schema_type == "number":
        return "float"
    if schema_type == "boolean":
        return "bool"
    if schema_type == "array":
        return "list[Any]"
    if schema_type == "object":
        return "dict[str, Any]"
    return "str"


def _safe_parameter_name(name: str) -> str:
    if name.isidentifier() and not keyword.iskeyword(name):
        return name
    return _safe_identifier(name)


def _path_expression(path: str, path_parameters: list[_MCPParameter]) -> str:
    expression = path
    for parameter in path_parameters:
        expression = expression.replace(
            "{" + parameter.name + "}",
            "{" + parameter.safe_name + "}",
        )
    if "{" not in expression:
        return json.dumps(expression)
    return f'f"{expression}"'


def _description(endpoint: APIEndpoint) -> str:
    return endpoint.summary or f"{endpoint.method} {endpoint.path}"


def _auth_headers(
    endpoint: APIEndpoint,
    auth_schemes: list[AuthScheme],
) -> list[_MCPAuthHeader]:
    schemes_by_name = {scheme.name: scheme for scheme in auth_schemes}
    headers: list[_MCPAuthHeader] = []
    for scheme_name in endpoint.auth_schemes:
        scheme = schemes_by_name.get(scheme_name)
        if scheme is None:
            continue
        if scheme.type == "apiKey" and scheme.api_key_in == "header":
            header_name = scheme.api_key_name or scheme.name
            headers.append(
                _MCPAuthHeader(
                    header_name=header_name,
                    env_var=_auth_env_var(scheme.name),
                    value_expression="api_key",
                )
            )
        elif scheme.type == "http" and scheme.scheme == "bearer":
            headers.append(
                _MCPAuthHeader(
                    header_name="Authorization",
                    env_var=_auth_env_var(scheme.name),
                    value_expression='f"Bearer {api_key}"',
                )
            )
    return headers


def _auth_env_var(scheme_name: str) -> str:
    stem = _safe_identifier(_camel_to_snake(scheme_name)).upper()
    if stem == "API_KEY":
        return "APIDIOM_API_KEY"
    return f"APIDIOM_{stem}_API_KEY"


def _body_hint(endpoint: APIEndpoint) -> str | None:
    if endpoint.request_schema is None:
        return None
    summary = _schema_summary(endpoint.request_schema.value)
    return f"Body schema: {summary}."


def _schema_summary(schema: dict[str, Any]) -> str:
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return ref.rsplit("/", 1)[-1]
    properties = schema.get("properties")
    if isinstance(properties, dict) and properties:
        names = ", ".join(str(name) for name in properties)
        return f"object with properties: {names}"
    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        return schema_type
    return "unconstrained JSON object"


def _include_endpoint(
    endpoint: APIEndpoint,
    spec: dict[str, Any],
    *,
    include_tags: list[str],
    include_operations: list[str],
) -> bool:
    if not include_tags and not include_operations:
        return True
    if include_tags and set(include_tags).intersection(_operation_tags(endpoint, spec)):
        return True
    for selector in include_operations:
        if _operation_selector_matches(endpoint, selector):
            return True
    return False


def _operation_tags(endpoint: APIEndpoint, spec: dict[str, Any]) -> list[str]:
    operation = _operation_for_endpoint(endpoint, spec)
    tags = operation.get("tags") if operation is not None else None
    if not isinstance(tags, list):
        return []
    return [tag for tag in tags if isinstance(tag, str)]


def _operation_selector_matches(endpoint: APIEndpoint, selector: str) -> bool:
    if ":" in selector:
        method, path = selector.split(":", 1)
        return endpoint.method == method.upper() and endpoint.path == path
    return selector in {
        endpoint.operation_id or "",
        _function_name(endpoint),
    }


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


def _default_base_url(spec: dict[str, Any]) -> str:
    servers = spec.get("servers")
    if isinstance(servers, list):
        for server in servers:
            if isinstance(server, dict) and isinstance(server.get("url"), str):
                return cast(str, server["url"])
    return ""
