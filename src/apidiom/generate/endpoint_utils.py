from __future__ import annotations

import json
import keyword
from dataclasses import dataclass
from typing import Any, cast

from apidiom.generate.codegen import _camel_to_snake, _function_name, _safe_identifier
from apidiom.models import APIEndpoint, APIParameter, AuthScheme, OpenAPISchema


@dataclass(frozen=True)
class ToolParameter:
    name: str
    safe_name: str
    annotation: str
    required: bool
    schema: dict[str, Any]
    description: str | None = None


@dataclass(frozen=True)
class AuthHeader:
    header_name: str
    env_var: str
    value_expression: str


@dataclass(frozen=True)
class OperationSummary:
    selector: str
    function_name: str
    description: str
    tags: list[str]


def template_parameter(parameter: APIParameter) -> ToolParameter:
    return ToolParameter(
        name=parameter.name,
        safe_name=safe_parameter_name(parameter.name),
        annotation=python_type(parameter.schema_model.value),
        required=parameter.required,
        schema=parameter.schema_model.value,
        description=parameter.description,
    )


def python_type(schema: dict[str, Any]) -> str:
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


def extract_body_params(schema: OpenAPISchema | None) -> list[ToolParameter]:
    if schema is None:
        return []
    s = schema.value
    if s.get("type") != "object":
        return []
    props = s.get("properties")
    if not isinstance(props, dict) or not props:
        return []
    required = set(s.get("required") or [])
    result: list[ToolParameter] = []
    for name, prop_schema in props.items():
        schema_value = (
            cast(dict[str, Any], prop_schema) if isinstance(prop_schema, dict) else {}
        )
        annotation = python_type(schema_value)
        if annotation in {"list[Any]", "dict[str, Any]"}:
            return []
        result.append(
            ToolParameter(
                name=name,
                safe_name=safe_parameter_name(name),
                annotation=annotation,
                required=name in required,
                schema=schema_value,
                description=(
                    schema_value.get("description")
                    if isinstance(schema_value.get("description"), str)
                    else None
                ),
            )
        )
    return result


def safe_parameter_name(name: str) -> str:
    if name.isidentifier() and not keyword.iskeyword(name):
        return name
    return _safe_identifier(name)


def path_expression(path: str, path_parameters: list[ToolParameter]) -> str:
    expression = path
    for parameter in path_parameters:
        expression = expression.replace(
            "{" + parameter.name + "}",
            "{" + parameter.safe_name + "}",
        )
    if "{" not in expression:
        return json.dumps(expression)
    return f'f"{expression}"'


def description(endpoint: APIEndpoint) -> str:
    return endpoint.summary or f"{endpoint.method} {endpoint.path}"


def auth_headers(
    endpoint: APIEndpoint,
    auth_schemes: list[AuthScheme],
) -> list[AuthHeader]:
    schemes_by_name = {scheme.name: scheme for scheme in auth_schemes}
    headers: list[AuthHeader] = []
    for scheme_name in endpoint.auth_schemes:
        scheme = schemes_by_name.get(scheme_name)
        if scheme is None:
            continue
        if scheme.type == "apiKey" and scheme.api_key_in == "header":
            headers.append(
                AuthHeader(
                    header_name=scheme.api_key_name or scheme.name,
                    env_var=auth_env_var(scheme.name),
                    value_expression="api_key",
                )
            )
        elif scheme.type == "http" and scheme.scheme == "bearer":
            headers.append(
                AuthHeader(
                    header_name="Authorization",
                    env_var=auth_env_var(scheme.name),
                    value_expression='f"Bearer {api_key}"',
                )
            )
    return headers


def auth_env_var(scheme_name: str) -> str:
    stem = _safe_identifier(_camel_to_snake(scheme_name)).upper()
    if stem == "API_KEY":
        return "APIDIOM_API_KEY"
    return f"APIDIOM_{stem}_API_KEY"


def include_endpoint(
    endpoint: APIEndpoint,
    spec: dict[str, Any],
    *,
    include_tags: list[str],
    include_operations: list[str],
) -> bool:
    if not include_tags and not include_operations:
        return True
    if include_tags and set(include_tags).intersection(operation_tags(endpoint, spec)):
        return True
    return any(
        operation_selector_matches(endpoint, selector)
        for selector in include_operations
    )


def operation_tags(endpoint: APIEndpoint, spec: dict[str, Any]) -> list[str]:
    operation = operation_for_endpoint(endpoint, spec)
    tags = operation.get("tags") if operation is not None else None
    if not isinstance(tags, list):
        return []
    return [tag for tag in tags if isinstance(tag, str)]


def operation_selector_matches(endpoint: APIEndpoint, selector: str) -> bool:
    if ":" in selector:
        method, path = selector.split(":", 1)
        return endpoint.method == method.upper() and endpoint.path == path
    return selector in {
        endpoint.operation_id or "",
        _function_name(endpoint),
    }


def operation_for_endpoint(
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


def default_base_url(spec: dict[str, Any]) -> str:
    servers = spec.get("servers")
    if isinstance(servers, list):
        for server in servers:
            if isinstance(server, dict) and isinstance(server.get("url"), str):
                return cast(str, server["url"])
    return ""


def operation_base_url(endpoint: APIEndpoint, spec: dict[str, Any]) -> str:
    operation = operation_for_endpoint(endpoint, spec)
    if operation is not None:
        base_url = operation.get("x-apidiom-base-url")
        if isinstance(base_url, str):
            return base_url
    return default_base_url(spec)
