from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from apidiom.generate.codegen import _function_name
from apidiom.generate.endpoint_utils import (
    AuthHeader,
    ToolParameter,
    auth_headers,
    default_base_url,
    description,
    extract_body_params,
    include_endpoint,
    operation_base_url,
    path_expression,
    template_parameter,
)
from apidiom.models import APIClientModel, APIEndpoint

_TEMPLATE_DIR = Path(__file__).parent / "templates"


DescriptionEnricher = Callable[[APIEndpoint], str]


@dataclass(frozen=True)
class _LangChainEndpoint:
    function_name: str
    method: str
    base_url: str
    path_expression: str
    description: str
    body_hint: str | None
    parameters: list[ToolParameter]
    query_parameters: list[ToolParameter]
    body_params: list[ToolParameter]
    has_body: bool
    auth_headers: list[AuthHeader]


def generate_langchain_tools(
    spec: dict[str, Any],
    model: APIClientModel,
    *,
    include_tags: list[str] | None = None,
    include_operations: list[str] | None = None,
    enricher: DescriptionEnricher | None = None,
) -> str:
    endpoints = [
        endpoint
        for endpoint in model.endpoints
        if include_endpoint(
            endpoint,
            spec,
            include_tags=include_tags or [],
            include_operations=include_operations or [],
        )
    ]
    if not endpoints:
        raise ValueError("No OpenAPI endpoints matched LangChain filters.")
    template = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    ).get_template("langchain_tools.py.j2")
    tools_text = template.render(
        default_base_url=default_base_url(spec),
        endpoints=[
            _template_endpoint(endpoint, model, spec=spec, enricher=enricher)
            for endpoint in endpoints
        ],
    )
    return f"{tools_text.rstrip()}\n"


def _template_endpoint(
    endpoint: APIEndpoint,
    model: APIClientModel,
    *,
    spec: dict[str, Any],
    enricher: DescriptionEnricher | None = None,
) -> _LangChainEndpoint:
    path_parameters = [
        template_parameter(parameter) for parameter in endpoint.path_parameters
    ]
    query_parameters = [
        template_parameter(parameter) for parameter in endpoint.query_parameters
    ]
    all_parameters = (
        path_parameters
        + [parameter for parameter in query_parameters if parameter.required]
        + [parameter for parameter in query_parameters if not parameter.required]
    )
    body_params = extract_body_params(endpoint.request_schema)
    has_body = endpoint.request_schema is not None and not body_params
    return _LangChainEndpoint(
        function_name=_function_name(endpoint),
        method=endpoint.method,
        base_url=operation_base_url(endpoint, spec),
        path_expression=path_expression(endpoint.path, path_parameters),
        description=enricher(endpoint)
        if enricher is not None
        else description(endpoint),
        body_hint=_body_hint(endpoint) if has_body else None,
        parameters=all_parameters,
        query_parameters=query_parameters,
        body_params=body_params,
        has_body=has_body,
        auth_headers=auth_headers(endpoint, model.auth_schemes),
    )


def _body_hint(endpoint: APIEndpoint) -> str | None:
    if endpoint.request_schema is None:
        return None
    schema_type = endpoint.request_schema.value.get("type")
    if isinstance(schema_type, str):
        return f"Body schema: {schema_type}."
    return "Body schema: unconstrained JSON object."
