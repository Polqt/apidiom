import json
from typing import Any

from apidiom.ingest.openapi_ingest import normalize_openapi_document
from apidiom.llm.provider import LLMProvider, LLMResponse
from apidiom.pipeline import (
    ToolGenerationRequest,
    detect_input_kind,
    generate_agent_tools,
    generate_client,
    generate_langchain_tools,
    generate_mcp_server,
    generate_tool_schema,
)


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses

    def is_available(self) -> bool:
        return True

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        return LLMResponse(text=self.responses.pop(0), model="fake")


def _model_generator(spec_json: str) -> str:
    return "class Pet: ...\n"


def test_detect_input_kind_openapi_for_valid_spec() -> None:
    assert detect_input_kind("tests/fixtures/petstore.yaml") == "openapi"


def test_detect_input_kind_unstructured_for_plain_text_endpoint_blurb() -> None:
    assert detect_input_kind("GET /pets\nReturns a list of pets.") == "unstructured"


def test_detect_input_kind_unstructured_for_malformed_json() -> None:
    assert detect_input_kind('{"openapi": ') == "unstructured"


def test_detect_input_kind_unstructured_for_html_docs() -> None:
    html = "<html><body><h1>Pets API</h1><p>GET /pets returns pets.</p></body></html>"

    assert detect_input_kind(html) == "unstructured"


def test_detect_input_kind_unstructured_for_postman_collection() -> None:
    postman = json.dumps(
        {
            "info": {
                "name": "Pets",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [
                {
                    "name": "List pets",
                    "request": {"method": "GET", "url": {"path": ["pets"]}},
                }
            ],
        }
    )

    assert detect_input_kind(postman) == "unstructured"


def test_pipeline_structured_spec_returns_code_and_tier() -> None:
    result = generate_client(
        "tests/fixtures/petstore.yaml",
        provider=None,
        lang="python",
        codegen="builtin",
        model_generator=_model_generator,
    )

    assert result.generated_client is not None
    assert result.codegen_tier == "builtin"
    assert result.model.endpoint("GET", "/pets").operation_id == "listPets"
    assert result.input_kind == "openapi"
    assert result.input_kind_source == "detected"


def test_pipeline_generates_mcp_server_from_openapi_spec() -> None:
    result = generate_mcp_server("tests/fixtures/petstore.yaml")

    assert result.generated_client is not None
    assert result.codegen_tier == "mcp"
    assert "FastMCP" in result.generated_client
    assert "def list_pets" in result.generated_client
    assert "README.md" in result.generated_files
    assert "GET:/pets" in result.generated_files["README.md"]
    assert "APIDIOM_API_BASE_URL" in result.generated_files["README.md"]
    assert result.input_kind == "openapi"
    assert result.input_kind_source == "explicit"


def test_pipeline_passes_mcp_filters() -> None:
    result = generate_mcp_server(
        "tests/fixtures/petstore.yaml",
        include_operations=["GET:/pets/{petId}"],
    )

    assert result.generated_client is not None
    assert "def get_pet(" in result.generated_client
    assert "def list_pets(" not in result.generated_client


def test_pipeline_generates_langchain_tools_from_openapi_spec() -> None:
    result = generate_langchain_tools("tests/fixtures/petstore.yaml")

    assert result.generated_client is not None
    assert result.codegen_tier == "langchain"
    assert "from langchain_core.tools import tool" in result.generated_client
    assert "def list_pets(" in result.generated_client


def test_pipeline_generates_openai_tool_schema() -> None:
    result = generate_tool_schema(
        "tests/fixtures/petstore.yaml",
        schema_format="openai",
        include_operations=["GET:/pets/{petId}"],
    )

    assert result.generated_client is not None
    assert result.codegen_tier == "schema:openai"
    assert '"type": "function"' in result.generated_client
    assert '"name": "get_pet"' in result.generated_client


def test_pipeline_generates_agent_tools_from_request() -> None:
    result = generate_agent_tools(
        ToolGenerationRequest(
            target="schema",
            sources="tests/fixtures/petstore.yaml",
            schema_format="openai",
            include_operations=["GET:/pets/{petId}"],
        )
    )

    assert result.generated_client is not None
    assert result.codegen_tier == "schema:openai"
    assert '"name": "get_pet"' in result.generated_client


def test_pipeline_generates_mcp_server_from_multiple_specs() -> None:
    result = generate_mcp_server(
        ["tests/fixtures/petstore.yaml", "tests/fixtures/petstore.yaml"],
        include_operations=["GET:/pets"],
    )

    assert result.generated_client is not None
    assert result.model.title == "merged"
    assert result.generated_client.count("def list_pets(") == 1


def test_pipeline_merged_mcp_keeps_per_spec_base_urls() -> None:
    first = {
        "openapi": "3.1.0",
        "info": {"title": "First", "version": "1.0.0"},
        "servers": [{"url": "https://first.example.test"}],
        "paths": {
            "/pets": {
                "get": {
                    "operationId": "listPets",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    second = {
        "openapi": "3.1.0",
        "info": {"title": "Second", "version": "1.0.0"},
        "servers": [{"url": "https://second.example.test"}],
        "paths": {
            "/users": {
                "get": {
                    "operationId": "listUsers",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    result = generate_mcp_server([json.dumps(first), json.dumps(second)])

    assert result.generated_client is not None
    assert "https://first.example.test" in result.generated_client
    assert "https://second.example.test" in result.generated_client


def test_pipeline_mcp_generation_tolerates_real_world_spec_validation_noise() -> None:
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "Noisy API", "version": "1.0.0"},
        "paths": {
            "/deployments": {
                "get": {
                    "operationId": "listDeployments",
                    "parameters": [
                        {
                            "name": "callback",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "string",
                                "format": "uri",
                                "default": "",
                            },
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    result = generate_mcp_server(json.dumps(spec))

    assert result.generated_client is not None
    assert "def list_deployments(" in result.generated_client


def test_pipeline_discovers_openapi_spec_from_base_url(monkeypatch) -> None:
    calls: list[str] = []
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "Discovered API", "version": "1.0.0"},
        "paths": {"/pets": {"get": {"responses": {"200": {"description": "OK"}}}}},
    }

    def fake_discover(source: str) -> str:
        calls.append(source)
        return "https://api.example.test/openapi.json"

    monkeypatch.setattr("apidiom.pipeline.discover_openapi_spec", fake_discover)
    monkeypatch.setattr(
        "apidiom.pipeline.load_openapi_document",
        lambda *args, **kwargs: spec,
    )
    monkeypatch.setattr(
        "apidiom.pipeline.load_openapi",
        lambda *args, **kwargs: normalize_openapi_document(spec, "discovered"),
    )

    result = generate_mcp_server("https://api.example.test")

    assert calls == ["https://api.example.test"]
    assert result.generated_client is not None
    assert "FastMCP" in result.generated_client


def test_pipeline_unstructured_docs_returns_code_unknowns_and_tier() -> None:
    fragment: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "Search API", "version": "1.0.0"},
        "paths": {
            "/search": {
                "get": {
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "required": False,
                            "schema": {},
                            "x-apidiom-unknown": ["type"],
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    result = generate_client(
        "GET /search query q",
        provider=FakeProvider([json.dumps(fragment)]),
        lang="python",
        input_kind="unstructured",
        codegen="builtin",
        model_generator=_model_generator,
    )

    assert result.generated_client is not None
    assert result.codegen_tier == "builtin"
    assert any("type" in item for item in result.unverified_items)
    assert "# UNVERIFIED: type not specified in docs" in result.generated_client
    assert result.input_kind == "unstructured"
    assert result.input_kind_source == "explicit"


def test_pipeline_auto_detects_unstructured_docs() -> None:
    fragment: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "Pets API", "version": "1.0.0"},
        "paths": {"/pets": {"get": {"responses": {"200": {"description": "OK"}}}}},
    }

    result = generate_client(
        "GET /pets\nReturns pets.",
        provider=FakeProvider([json.dumps(fragment)]),
        lang="python",
        codegen="builtin",
        model_generator=_model_generator,
    )

    assert result.generated_client is not None
    assert result.input_kind == "unstructured"
    assert result.input_kind_source == "detected"


def test_pipeline_explicit_openapi_override_does_not_redetect() -> None:
    try:
        generate_client(
            "GET /pets\nReturns pets.",
            provider=FakeProvider([]),
            lang="python",
            input_kind="openapi",
            codegen="builtin",
            model_generator=_model_generator,
        )
    except RuntimeError as exc:
        assert "Could not parse OpenAPI document" in str(exc)
    else:
        raise AssertionError("explicit openapi override should force OpenAPI parsing")


def test_pipeline_explicit_unstructured_override_does_not_redetect_clean_spec() -> None:
    fragment: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "Pets API", "version": "1.0.0"},
        "paths": {"/pets": {"get": {"responses": {"200": {"description": "OK"}}}}},
    }

    result = generate_client(
        "tests/fixtures/petstore.yaml",
        provider=FakeProvider([json.dumps(fragment)]),
        lang="python",
        input_kind="unstructured",
        codegen="builtin",
        model_generator=_model_generator,
    )

    assert result.input_kind == "unstructured"
    assert result.input_kind_source == "explicit"
