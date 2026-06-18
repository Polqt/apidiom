import json
from typing import Any

from apidiom.generate.schema_gen import generate_tool_schema
from apidiom.ingest.openapi_ingest import normalize_openapi_document


def _spec() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Tiny API", "version": "1.0.0"},
        "paths": {
            "/pets/{petId}": {
                "get": {
                    "operationId": "getPet",
                    "summary": "Get pet by ID",
                    "parameters": [
                        {
                            "name": "petId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }


def test_generate_anthropic_tool_schema() -> None:
    spec = _spec()
    model = normalize_openapi_document(spec, "test")

    payload = json.loads(generate_tool_schema(spec, model, schema_format="anthropic"))

    assert payload[0]["name"] == "get_pet"
    assert payload[0]["input_schema"]["properties"]["petId"]["type"] == "integer"
    assert payload[0]["input_schema"]["required"] == ["petId"]


def test_generate_openai_tool_schema() -> None:
    spec = _spec()
    model = normalize_openapi_document(spec, "test")

    payload = json.loads(generate_tool_schema(spec, model, schema_format="openai"))

    assert payload[0]["type"] == "function"
    assert payload[0]["function"]["name"] == "get_pet"
    assert payload[0]["function"]["parameters"]["required"] == ["petId"]
