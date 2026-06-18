from typing import Any

from apidiom.generate.mcp import (
    generate_mcp_server,
    list_mcp_operations,
    validate_mcp_server_text,
)
from apidiom.ingest.openapi_ingest import normalize_openapi_document


def _small_spec() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Tiny API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.test"}],
        "components": {
            "securitySchemes": {
                "api_key": {"type": "apiKey", "name": "x-api-key", "in": "header"},
                "bearerAuth": {"type": "http", "scheme": "bearer"},
            }
        },
        "paths": {
            "/pets": {
                "get": {
                    "operationId": "listPets",
                    "summary": "List pets",
                    "tags": ["pets"],
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "description": "Maximum pets to return",
                            "schema": {"type": "integer"},
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "createPet",
                    "summary": "Create a pet",
                    "tags": ["pets"],
                    "security": [{"api_key": []}],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"name": {"type": "string"}},
                                }
                            }
                        }
                    },
                    "responses": {"201": {"description": "Created"}},
                },
            },
            "/pets/{petId}": {
                "get": {
                    "operationId": "getPet",
                    "summary": "Info for a specific pet",
                    "security": [{"bearerAuth": []}],
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
            },
        },
    }


def test_generate_mcp_server_emits_runnable_fastmcp_tools() -> None:
    spec = _small_spec()
    model = normalize_openapi_document(spec, "test")

    server = generate_mcp_server(spec, model)

    assert "from mcp.server.fastmcp import FastMCP" in server
    assert 'mcp = FastMCP("tiny_api")' in server
    assert 'DEFAULT_BASE_URL = "https://api.example.test"' in server
    assert "@mcp.tool()" in server
    assert "def list_pets(" in server
    assert "limit: int | None = None" in server
    assert '"""List pets' in server
    assert 'params["limit"] = limit' in server
    assert "def create_pet(" in server
    assert "name: str | None = None" in server
    assert 'json_body["name"] = name' in server
    assert "    body: dict[str, Any] | None = None," not in server
    assert 'os.environ.get("APIDIOM_API_KEY")' in server
    assert 'os.environ.get("APIDIOM_BEARER_AUTH_API_KEY")' in server
    assert 'headers["Authorization"] = f"Bearer {api_key}"' in server
    assert 'headers["x-api-key"] = api_key' in server
    assert 'path = f"/pets/{petId}"' in server
    assert "def get_pet(" in server
    assert "petId: int" in server
    assert 'return _request_json(\n        "GET",' in server
    assert "mcp.run()" in server
    compile(server, "generated_tiny_mcp.py", "exec")


def test_generate_mcp_server_falls_back_to_method_path_names() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "Fallback API", "version": "1.0.0"},
        "paths": {
            "/search-items": {"get": {"responses": {"200": {"description": "OK"}}}}
        },
    }
    model = normalize_openapi_document(spec, "test")

    server = generate_mcp_server(spec, model)

    assert "def get_search_items(" in server


def test_generate_mcp_server_filters_by_tag() -> None:
    spec = _small_spec()
    model = normalize_openapi_document(spec, "test")

    server = generate_mcp_server(spec, model, include_tags=["pets"])

    assert "def list_pets(" in server
    assert "def create_pet(" in server
    assert "def get_pet(" not in server


def test_generate_mcp_server_filters_by_include_selector() -> None:
    spec = _small_spec()
    model = normalize_openapi_document(spec, "test")

    server = generate_mcp_server(spec, model, include_operations=["GET:/pets/{petId}"])

    assert "def get_pet(" in server
    assert "def list_pets(" not in server
    assert "def create_pet(" not in server


def test_generate_mcp_server_rejects_empty_filter_result() -> None:
    spec = _small_spec()
    model = normalize_openapi_document(spec, "test")

    try:
        generate_mcp_server(spec, model, include_tags=["missing"])
    except ValueError as exc:
        assert "No OpenAPI endpoints matched MCP filters" in str(exc)
    else:
        raise AssertionError("empty MCP filter should fail")


def test_validate_mcp_server_text_reports_tools_and_env_vars() -> None:
    spec = _small_spec()
    model = normalize_openapi_document(spec, "test")
    server = generate_mcp_server(spec, model)

    check = validate_mcp_server_text(server)

    assert check.tool_count == 3
    assert "APIDIOM_API_BASE_URL" in check.env_vars
    assert "APIDIOM_API_KEY" in check.env_vars
    assert "APIDIOM_BEARER_AUTH_API_KEY" in check.env_vars


def test_generate_mcp_server_decomposes_simple_object_body() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "Pay API", "version": "1.0.0"},
        "paths": {
            "/charge": {
                "post": {
                    "operationId": "createCharge",
                    "summary": "Create charge",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["amount", "currency"],
                                    "properties": {
                                        "amount": {"type": "integer"},
                                        "currency": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    model = normalize_openapi_document(spec, "test")

    server = generate_mcp_server(spec, model)

    assert "amount: int," in server
    assert "currency: str," in server
    assert "description: str | None = None," in server
    assert "    body: dict[str, Any] | None = None," not in server
    assert 'json_body["amount"] = amount' in server
    assert 'json_body["currency"] = currency' in server
    assert 'json_body["description"] = description' in server
    compile(server, "generated_pay_mcp.py", "exec")


def test_generate_mcp_server_keeps_body_dict_for_complex_schema() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "Complex API", "version": "1.0.0"},
        "paths": {
            "/items": {
                "post": {
                    "operationId": "createItem",
                    "summary": "Create item",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "tags": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    model = normalize_openapi_document(spec, "test")

    server = generate_mcp_server(spec, model)

    assert "    body: dict[str, Any] | None = None," in server
    assert "    json_body: dict[str, Any] = {}" not in server
    compile(server, "generated_complex_mcp.py", "exec")


def test_list_mcp_operations_reports_copyable_selectors() -> None:
    spec = _small_spec()
    model = normalize_openapi_document(spec, "test")

    operations = list_mcp_operations(spec, model, include_tags=["pets"])

    assert [operation.selector for operation in operations] == [
        "GET:/pets",
        "POST:/pets",
    ]
    assert operations[0].function_name == "list_pets"
    assert operations[0].description == "List pets"
    assert operations[0].tags == ["pets"]
