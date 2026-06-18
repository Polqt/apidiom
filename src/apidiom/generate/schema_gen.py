from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal

from apidiom.generate.codegen import _function_name
from apidiom.generate.endpoint_utils import (
    description,
    extract_body_params,
    include_endpoint,
    template_parameter,
)
from apidiom.models import APIClientModel, APIEndpoint

SchemaFormat = Literal["anthropic", "openai"]


DescriptionEnricher = Callable[[APIEndpoint], str]


def generate_tool_schema(
    spec: dict[str, Any],
    model: APIClientModel,
    *,
    schema_format: SchemaFormat = "anthropic",
    include_tags: list[str] | None = None,
    include_operations: list[str] | None = None,
    enricher: DescriptionEnricher | None = None,
) -> str:
    tools = [
        _tool_schema(endpoint, enricher=enricher)
        for endpoint in model.endpoints
        if include_endpoint(
            endpoint,
            spec,
            include_tags=include_tags or [],
            include_operations=include_operations or [],
        )
    ]
    if not tools:
        raise ValueError("No OpenAPI endpoints matched schema filters.")
    if schema_format == "anthropic":
        payload: object = tools
    elif schema_format == "openai":
        payload = [
            {
                "type": "function",
                "function": {
                    "name": tool_schema["name"],
                    "description": tool_schema["description"],
                    "parameters": tool_schema["input_schema"],
                },
            }
            for tool_schema in tools
        ]
    else:
        raise ValueError("Schema format must be 'anthropic' or 'openai'.")
    return f"{json.dumps(payload, indent=2)}\n"


def _tool_schema(
    endpoint: APIEndpoint,
    *,
    enricher: DescriptionEnricher | None,
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []

    for parameter in endpoint.path_parameters + endpoint.query_parameters:
        tool_parameter = template_parameter(parameter)
        properties[tool_parameter.name] = _json_schema(
            tool_parameter.schema,
            description=tool_parameter.description,
        )
        if tool_parameter.required:
            required.append(tool_parameter.name)

    body_params = extract_body_params(endpoint.request_schema)
    if body_params:
        for body_parameter in body_params:
            properties[body_parameter.name] = _json_schema(
                body_parameter.schema,
                description=body_parameter.description,
            )
            if body_parameter.required:
                required.append(body_parameter.name)
    elif endpoint.request_schema is not None:
        properties["body"] = _json_schema(endpoint.request_schema.value)

    return {
        "name": _function_name(endpoint),
        "description": (
            enricher(endpoint) if enricher is not None else description(endpoint)
        ),
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def _json_schema(
    schema: dict[str, Any],
    *,
    description: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    schema_type = schema.get("type")
    result["type"] = schema_type if isinstance(schema_type, str) else "string"
    schema_description = schema.get("description")
    if isinstance(schema_description, str):
        result["description"] = schema_description
    elif description is not None:
        result["description"] = description
    return result
