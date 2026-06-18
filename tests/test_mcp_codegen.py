from typing import Any

from apidiom.generate.mcp import generate_mcp_server
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
    assert "body: dict[str, Any] | None = None" in server
    assert 'os.environ.get("APIDIOM_API_KEY")' in server
    assert 'os.environ.get("APIDIOM_BEARER_AUTH_API_KEY")' in server
    assert 'headers["Authorization"] = f"Bearer {api_key}"' in server
    assert 'headers["x-api-key"] = api_key' in server
    assert "Body schema: object with properties: name." in server
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
